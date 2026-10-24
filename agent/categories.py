"""类别定义：key -> (中文名, 颜色)。

CLI 报表与 Web 端共用这一份调色板；新增类别只需在这里补一行，
并保持 rules/*.json 里引用的 category 与此一致。
"""

from typing import Tuple

CATEGORIES = {
    "dev": ("开发", "#3B82F6"),
    "work": ("办公", "#0EA5E9"),
    "im": ("沟通", "#10B981"),
    "video": ("视频", "#EF4444"),
    "music": ("音乐", "#22D3EE"),
    "game": ("游戏", "#8B5CF6"),
    "design": ("设计", "#F43F5E"),
    "browse-fun": ("娱乐浏览", "#F97316"),
    "browse-dev": ("技术浏览", "#6366F1"),
    "ai": ("AI 助手", "#14B8A6"),
    "shopping": ("购物", "#EC4899"),
    "browser": ("浏览器", "#94A3B8"),
    "tool": ("工具", "#64748B"),
    "idle": ("离开", "#475569"),
    "other": ("其他", "#A1A1AA"),
}

DEFAULT_COLOR = "#A1A1AA"


def category_label(key: str) -> str:
    return CATEGORIES.get(key, (key, DEFAULT_COLOR))[0]


def category_color(key: str) -> str:
    return CATEGORIES.get(key, ("", DEFAULT_COLOR))[1]


def legend() -> dict:
    """Web 端 /api/meta 使用。"""
    return {k: {"name": v[0], "color": v[1]} for k, v in CATEGORIES.items()}


def main_categories() -> Tuple[str, ...]:
    """除 idle 外的类别（报表里 idle 单列）。"""
    return tuple(k for k in CATEGORIES if k != "idle")
