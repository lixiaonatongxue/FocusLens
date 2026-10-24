"""Win32 API 封装（纯 ctypes，零第三方依赖）。

只使用任何桌面应用都可调用的普通接口：
- 读取当前前台窗口的进程名与标题
- 读取全局最近一次键鼠输入时间（用于空闲判断）
- 订阅前台窗口切换事件

不做键盘记录、不截屏、不联网。
"""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import POINTER, WINFUNCTYPE, byref, c_int, c_uint, wintypes
from typing import Callable, Optional, Tuple

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000
PM_REMOVE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

HWINEVENTHOOK = wintypes.HANDLE

WinEventProc = WINFUNCTYPE(
    None,
    HWINEVENTHOOK,    # hHook
    wintypes.DWORD,   # event
    wintypes.HWND,    # hwnd
    wintypes.LONG,    # idObject
    wintypes.LONG,    # idChild
    wintypes.DWORD,   # dwEventThread
    wintypes.DWORD,   # dwmsEventTime
)


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


# 显式声明句柄相关签名，避免 64 位下指针被截断
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, c_int]
user32.GetWindowTextW.restype = c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, POINTER(wintypes.DWORD)]
user32.SetWinEventHook.argtypes = [
    c_uint, c_uint, wintypes.HINSTANCE, WinEventProc, c_uint, c_uint, c_uint,
]
user32.SetWinEventHook.restype = HWINEVENTHOOK
user32.UnhookWinEvent.argtypes = [HWINEVENTHOOK]
user32.UnhookWinEvent.restype = wintypes.BOOL
user32.PeekMessageW.argtypes = [POINTER(wintypes.MSG), wintypes.HWND, c_uint, c_uint, c_uint]
user32.PeekMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [POINTER(wintypes.MSG)]
user32.GetLastInputInfo.argtypes = [POINTER(LASTINPUTINFO)]
user32.GetLastInputInfo.restype = wintypes.BOOL

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.GetTickCount.restype = wintypes.DWORD


def idle_milliseconds() -> int:
    """距离全局最近一次键鼠输入过去的毫秒数。"""
    info = LASTINPUTINFO(cbSize=ctypes.sizeof(LASTINPUTINFO), dwTime=0)
    if not user32.GetLastInputInfo(byref(info)):
        return 0
    return (kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF


def _process_name(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, byref(size)):
            return os.path.basename(buf.value)
        return ""
    finally:
        kernel32.CloseHandle(handle)


def foreground_info() -> Optional[Tuple[str, str, int]]:
    """当前前台窗口 (exe 进程名, 窗口标题, pid)；取不到时返回 None。"""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, byref(pid))
    title = ctypes.create_unicode_buffer(1024)
    user32.GetWindowTextW(hwnd, title, 1024)
    exe = _process_name(pid.value) or "?"
    return exe, title.value, pid.value


class ForegroundHook:
    """SetWinEventHook 前台切换订阅。

    注意：必须保活回调引用（存在实例属性上），否则被 GC 后回调指针悬空会崩溃。
    注册钩子的线程需要持续泵消息（见 pump_messages），事件才会派发。
    """

    def __init__(self, on_event: Callable[[], None]):
        self._proc = WinEventProc(lambda *args: on_event())
        self._hook = user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND,
            None, self._proc, 0, 0, WINEVENT_OUTOFCONTEXT,
        )
        if not self._hook:
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if getattr(self, "_hook", None):
            user32.UnhookWinEvent(self._hook)
            self._hook = None


def pump_messages(should_stop: Callable[[], bool], poll_seconds: float = 0.1) -> None:
    """消息泵：out-of-context 的 WinEvent 事件依赖消息循环派发。

    用 PeekMessage 轮询而不是阻塞的 GetMessage，保证停止信号/Ctrl+C 能被及时处理。
    """
    msg = wintypes.MSG()
    while not should_stop():
        while user32.PeekMessageW(byref(msg), None, 0, 0, PM_REMOVE):
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))
        time.sleep(poll_seconds)
