"""合成演示数据：空库时快速预览报表效果。行程全部虚构，不含任何真实数据。"""

from __future__ import annotations

from datetime import date, datetime

from .classifier import Classifier
from .store import Store


def _ts(day: date, hh: int, mm: int = 0) -> int:
    start = int(datetime.combine(day, datetime.min.time()).timestamp())
    return start + hh * 3600 + mm * 60


def _hm(text: str):
    hh, mm = text.split(":")
    return int(hh), int(mm)


# 一位开发者的一天（虚构）：写代码、查资料、摸鱼、午休
PLAN = [
    ("08:32", "09:05", "WeChat.exe", "微信"),
    ("09:05", "10:40", "Code.exe", "collector.py - FocusLens - Visual Studio Code"),
    ("10:40", "10:58", "chrome.exe", "SetWinEventHook 用法 - 搜索"),
    ("10:58", "11:30", "Code.exe", "collector.py - FocusLens - Visual Studio Code"),
    ("11:30", "12:12", "chrome.exe", "【4K】治愈合集 (゜-゜)つロ 干杯~ - 哔哩哔哩"),
    ("12:12", "13:35", None, None),  # 午休离开
    ("13:35", "15:05", "Code.exe", "server.py - FocusLens - Visual Studio Code"),
    ("15:05", "15:26", "chrome.exe", "focuslens/focuslens: local screen time for Windows - GitHub"),
    ("15:26", "16:10", "Code.exe", "app.js - FocusLens - Visual Studio Code"),
    ("16:10", "16:45", "cloudmusic.exe", "网易云音乐"),
    ("16:45", "17:25", "Code.exe", "app.js - FocusLens - Visual Studio Code"),
    ("17:25", "17:55", "WeChat.exe", "微信"),
    ("17:55", "18:35", "chrome.exe", "Windows 屏幕时间统计工具有哪些？ - 知乎"),
]


def seed_demo(store: Store, classifier: Classifier, force: bool = False, day: date = None) -> int:
    day = day or date.today()
    day_start = _ts(day, 0)
    if not force and store.events_between(day_start, day_start + 86400):
        raise SystemExit("今天已有数据；确认要混入演示数据请加 --force")
    now_limit = datetime.now().timestamp()
    n = 0
    for s, e, exe, title in PLAN:
        ts = _ts(day, *_hm(s))
        te = min(_ts(day, *_hm(e)), now_limit)  # 不写入"未来"的时间
        if te <= ts:
            continue
        if exe is None:
            store.add_event(ts, te, "", "", "idle")
        else:
            category = classifier.classify(exe, title).category
            store.add_event(ts, te, exe, "", category)  # 与默认隐私一致：不落盘标题
        n += 1
    return n
