"""前台会话采集状态机。

线程模型：
- 主线程：SetWinEventHook 事件驱动（窗口切换立刻采样）+ 消息泵；
- 轮询线程：每 poll_interval 秒兜底采样（防漏事件、标题变化、空闲判断）。

段（segment）定义：同一 (exe, title) 且未离开的一次连续前台使用。
空闲判定：距最后一次键鼠输入超过 idle_seconds。判定离开时，当前应用段
截止于「最后输入时刻 + idle_seconds」（宽限窗记给应用），其后记为 idle 段，
直到出现新的输入。锁屏（LogonUI.exe）由规则直接归入 idle。
"""

from __future__ import annotations

import hashlib
import signal
import threading
import time
from typing import Callable, Optional

from .classifier import Classifier
from .store import Store

PRIVACY_LEVELS = ("default", "full", "hash")


def _default_idle_ms() -> int:
    from . import winapi

    return winapi.idle_milliseconds()


def _default_foreground() -> Optional[tuple]:
    from . import winapi

    return winapi.foreground_info()


class Collector:
    def __init__(
        self,
        store: Store,
        classifier: Classifier,
        *,
        idle_seconds: float = 300,
        poll_interval: float = 1.0,
        privacy: str = "default",
        now_fn: Callable[[], float] = time.time,
        idle_ms_fn: Callable[[], int] = _default_idle_ms,
        foreground_fn: Callable[[], Optional[tuple]] = _default_foreground,
        on_event: Optional[Callable[[dict], None]] = None,
    ):
        if privacy not in PRIVACY_LEVELS:
            raise ValueError(f"unknown privacy level: {privacy!r}")
        self.store = store
        self.classifier = classifier
        self.idle_seconds = idle_seconds
        self.poll_interval = poll_interval
        self.privacy = privacy
        self._now = now_fn
        self._idle_ms = idle_ms_fn
        self._foreground = foreground_fn
        self._on_event = on_event
        self._lock = threading.Lock()
        self._cur: Optional[dict] = None
        self._prev_end: Optional[float] = None
        self._last_wall: Optional[float] = None
        self._stop = threading.Event()
        self._poller: Optional[threading.Thread] = None

    # -- 采样与切分 -------------------------------------------------------

    def sample(self) -> None:
        """读取一次系统状态，必要时结束/开启段。线程安全。"""
        now = self._now()
        with self._lock:
            # 采样间隙过大（睡眠/休眠/进程被挂起）：当前段封在上次采样点，
            # 不把睡眠时间记进任何应用。
            if self._last_wall is not None:
                if now - self._last_wall > max(60.0, self.poll_interval * 10):
                    self._close(self._last_wall + self.poll_interval)
            self._last_wall = now

            idle_ms = self._idle_ms()
            info = self._foreground()
            away = info is None or idle_ms >= self.idle_seconds * 1000

            if away:
                last_input = now - idle_ms / 1000.0
                if self._cur is not None and self._cur["kind"] == "app":
                    end = min(now, last_input + self.idle_seconds)
                    self._close(end)
                    self._cur = _idle_segment(end)
                # 已经处于 idle 段：继续等待
            else:
                resume = now - idle_ms / 1000.0
                if self._cur is not None and self._cur["kind"] == "idle":
                    self._close(max(self._cur["start"], resume))
                exe, title, _pid = info
                cur = self._cur
                same_window = (
                    cur is not None
                    and cur["kind"] == "app"
                    and cur["exe"] == exe
                    and cur["title"] == title
                )
                if not same_window:
                    self._close(now)
                    result = self.classifier.classify(exe, title)
                    start = now if self._prev_end is None else max(resume, self._prev_end)
                    self._cur = {
                        "kind": "app",
                        "exe": exe,
                        "title": title,
                        "category": result.category,
                        "name": result.name,
                        "start": start,
                    }

    def flush(self) -> None:
        """结束并落盘当前段（停止采集时调用）。"""
        with self._lock:
            self._close(self._now())

    def _close(self, end: float) -> None:
        cur = self._cur
        if cur is None:
            return
        end = max(end, cur["start"])
        self._prev_end = end
        self._cur = None
        title_stored = self._stored_title(cur["title"])
        self.store.add_event(cur["start"], end, cur.get("exe", ""), title_stored, cur["category"])
        if self._on_event is not None and end > cur["start"]:
            self._on_event(
                {
                    "start": int(cur["start"]),
                    "end": int(end),
                    "duration": int(end - cur["start"]),
                    "exe": cur.get("exe", ""),
                    "name": cur.get("name", "离开"),
                    "title": title_stored,
                    "category": cur["category"],
                }
            )

    def _stored_title(self, title: str) -> str:
        if self.privacy == "full":
            return title
        if self.privacy == "hash":
            if not title:
                return ""
            return hashlib.sha1(title.encode("utf-8", "ignore")).hexdigest()[:16]
        return ""  # default：只存进程名与类别

    # -- 生命周期 ---------------------------------------------------------

    def start_poller(self) -> None:
        self._poller = threading.Thread(
            target=self._poll_loop, name="focuslens-poller", daemon=True
        )
        self._poller.start()

    def _poll_loop(self) -> None:
        while not self._stop.wait(self.poll_interval):
            try:
                self.sample()
            except Exception:  # 单次采样失败不应终止采集
                continue

    def stop(self) -> None:
        self._stop.set()
        if self._poller is not None:
            self._poller.join(timeout=3)
        self.flush()

    def run_forever(self, duration: Optional[float] = None) -> None:
        """阻塞运行：安装前台钩子并泵消息；duration 秒后自动停止（None=直到 Ctrl+C）。"""
        from . import winapi

        stop = threading.Event()

        def _handle_sig(signum, frame):
            stop.set()

        old_int = signal.signal(signal.SIGINT, _handle_sig)
        old_break = None
        try:
            old_break = signal.signal(signal.SIGBREAK, _handle_sig)
        except (AttributeError, ValueError, OSError):
            pass

        self.start_poller()
        hook = None
        try:
            hook = winapi.ForegroundHook(self.sample)
            self.sample()
            if duration is not None:
                timer = threading.Timer(duration, stop.set)
                timer.daemon = True
                timer.start()
            print("采集中… Ctrl+C 停止")
            winapi.pump_messages(stop.is_set)
        finally:
            if hook is not None:
                hook.close()
            signal.signal(signal.SIGINT, old_int)
            if old_break is not None:
                try:
                    signal.signal(signal.SIGBREAK, old_break)
                except (ValueError, OSError):
                    pass
            self.stop()


def _idle_segment(start: float) -> dict:
    return {
        "kind": "idle",
        "exe": "",
        "title": "",
        "category": "idle",
        "name": "离开",
        "start": start,
    }
