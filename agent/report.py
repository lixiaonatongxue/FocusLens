"""报表聚合与文本渲染：今日 / 近 7 天。

跨午夜的事件在查询时按当天边界裁剪，两天各记各的。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .categories import category_label
from .classifier import Classifier
from .store import Event, Store

FOCUS_DEFAULTS = {
    "focus_categories": ["dev"],
    "focus_merge_gap_seconds": 300,
    "focus_min_session_seconds": 900,
}


def human_duration(sec) -> str:
    sec = int(sec)
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}小时{m}分钟"
    if m:
        return f"{m}分{s}秒"
    return f"{s}秒"


def parse_date(text: str) -> date:
    return datetime.strptime(text, "%Y-%m-%d").date()


def day_bounds(day: date) -> Tuple[int, int]:
    start = int(datetime.combine(day, datetime.min.time()).timestamp())
    return start, start + 86400


def clipped(events: Iterable[Event], start_ts: int, end_ts: int) -> Iterable[Event]:
    """把与 [start_ts, end_ts) 相交的事件裁剪到该区间内。"""
    for e in events:
        s, t = max(e.start_ts, start_ts), min(e.end_ts, end_ts)
        if t > s:
            yield Event(s, t, e.exe, e.title, e.category)


def category_totals(events: Iterable[Event]) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    for e in events:
        totals[e.category] = totals.get(e.category, 0) + e.duration
    return totals


def top_apps(events: Iterable[Event], classifier: Classifier, top_n: int = 5) -> List[dict]:
    agg: Dict[str, dict] = {}
    for e in events:
        if e.category == "idle":
            continue
        name = classifier.classify(e.exe, e.title).name
        item = agg.setdefault(
            name, {"name": name, "exe": e.exe, "category": e.category, "seconds": 0}
        )
        item["seconds"] += e.duration
    return sorted(agg.values(), key=lambda x: -x["seconds"])[:top_n]


def focus_sessions(
    events: Iterable[Event],
    categories: Set[str],
    merge_gap: int = 300,
    min_len: int = 900,
) -> List[Tuple[int, int, int]]:
    """专注时段：专注类事件相邻间隔 <= merge_gap 秒合并为一段，只保留 >= min_len。"""
    focus = sorted((e for e in events if e.category in categories), key=lambda e: e.start_ts)
    sessions: List[List[int]] = []
    for e in focus:
        if sessions and e.start_ts - sessions[-1][1] <= merge_gap:
            sessions[-1][1] = max(sessions[-1][1], e.end_ts)
            sessions[-1][2] += e.duration
        else:
            sessions.append([e.start_ts, e.end_ts, e.duration])
    return [tuple(s) for s in sessions if s[2] >= min_len]


def summarize_day(
    store: Store,
    classifier: Classifier,
    day: date,
    focus_cfg: Optional[dict] = None,
    detail: bool = True,
) -> dict:
    cfg = {**FOCUS_DEFAULTS, **(focus_cfg or {})}
    start, end = day_bounds(day)
    events = list(clipped(store.events_between(start, end), start, end))
    totals = category_totals(events)
    sessions = focus_sessions(
        events,
        set(cfg["focus_categories"]),
        cfg["focus_merge_gap_seconds"],
        cfg["focus_min_session_seconds"],
    )
    result = {
        "date": day.isoformat(),
        "weekday": "周" + "一二三四五六日"[day.weekday()],
        "totals": totals,
        "active_seconds": sum(v for k, v in totals.items() if k != "idle"),
        "idle_seconds": totals.get("idle", 0),
        "segment_count": len(events),
        "focus": {
            "total_seconds": sum(s[2] for s in sessions),
            "count": len(sessions),
            "longest_seconds": max((s[2] for s in sessions), default=0),
            "sessions": [
                {"start": s[0], "end": s[1], "seconds": s[2]} for s in sessions
            ],
        },
    }
    if detail:
        result["top_apps"] = top_apps(events, classifier)
        result["timeline"] = [
            {
                "start": e.start_ts,
                "end": e.end_ts,
                "category": e.category,
                "exe": e.exe,
                "app": "离开" if e.category == "idle" else classifier.classify(e.exe, e.title).name,
            }
            for e in events
        ]
    return result


def summarize_days(
    store: Store, classifier: Classifier, days: List[date], focus_cfg: Optional[dict] = None
) -> List[dict]:
    out = []
    for d in days:
        s = summarize_day(store, classifier, d, focus_cfg, detail=False)
        out.append(
            {
                "date": s["date"],
                "totals": s["totals"],
                "active_seconds": s["active_seconds"],
                "idle_seconds": s["idle_seconds"],
            }
        )
    return out


# -- 文本渲染 ------------------------------------------------------------


def render_day(
    store: Store,
    classifier: Classifier,
    day: Optional[date] = None,
    focus_cfg: Optional[dict] = None,
) -> str:
    day = day or date.today()
    s = summarize_day(store, classifier, day, focus_cfg)
    lines = [f"FocusLens · {s['date']}（{s['weekday']}）", "=" * 44]
    if not s["totals"]:
        lines.append("暂无记录。运行 `python run.py collect` 开始采集。")
        return "\n".join(lines)

    total = s["active_seconds"] + s["idle_seconds"] or 1
    lines.append(
        f"活跃 {human_duration(s['active_seconds'])}   "
        f"离开 {human_duration(s['idle_seconds'])}   {s['segment_count']} 段"
    )
    lines.append("")
    lines.append("类别占比：")
    for cat, sec in sorted(s["totals"].items(), key=lambda kv: -kv[1]):
        bar = "█" * max(1, round(sec / total * 24))
        lines.append(f"  {category_label(cat):　<5}{bar} {human_duration(sec)} ({sec / total * 100:.0f}%)")

    lines.append("")
    lines.append("Top 应用：")
    for i, app in enumerate(s["top_apps"], 1):
        lines.append(f"  {i}. {app['name']}（{app['exe']}） {human_duration(app['seconds'])}")

    f = s["focus"]
    cats = "/".join((focus_cfg or {}).get("focus_categories", FOCUS_DEFAULTS["focus_categories"]))
    lines.append("")
    lines.append(
        f"专注时段（{cats}，≥15 分钟）：共 {human_duration(f['total_seconds'])}，"
        f"{f['count']} 段，最长 {human_duration(f['longest_seconds'])}"
    )
    for sess in sorted(f["sessions"], key=lambda x: -x["seconds"])[:5]:
        c1 = datetime.fromtimestamp(sess["start"]).strftime("%H:%M")
        c2 = datetime.fromtimestamp(sess["end"]).strftime("%H:%M")
        lines.append(f"  {c1}–{c2}  {human_duration(sess['seconds'])}")
    return "\n".join(lines)


def render_week(store: Store, classifier: Classifier, focus_cfg: Optional[dict] = None) -> str:
    today = date.today()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    lines = [f"FocusLens · 近 7 天（{days[0]} ~ {days[-1]}）", "=" * 44]
    agg: Dict[str, int] = {}
    for d in days:
        s = summarize_day(store, classifier, d, focus_cfg, detail=False)
        lines.append(
            f"  {d}（周{'一二三四五六日'[d.weekday()]}） "
            f"活跃 {human_duration(s['active_seconds'])} / 离开 {human_duration(s['idle_seconds'])}"
        )
        for k, v in s["totals"].items():
            agg[k] = agg.get(k, 0) + v
    total = sum(agg.values()) or 1
    lines.append("")
    lines.append("7 天类别合计：")
    for cat, sec in sorted(agg.items(), key=lambda kv: -kv[1]):
        bar = "█" * max(1, round(sec / total * 24))
        lines.append(f"  {category_label(cat):　<5}{bar} {human_duration(sec)} ({sec / total * 100:.0f}%)")
    return "\n".join(lines)
