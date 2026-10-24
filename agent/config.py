"""配置加载：内置默认值 + 可选的本地 config.json 覆盖。

config.json 不入库（.gitignore），首次使用可从 config.example.json 复制。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULTS: Dict[str, Any] = {
    "idle_seconds": 300,
    "poll_interval": 1.0,
    # default=不存标题 / full=存标题 / hash=只存标题哈希（用于区分同类文档但不可回读）
    "privacy": "default",
    "port": 8810,
    "db_path": "data/focuslens.db",
    # 同一窗口停留超过该秒数时周期性落盘（报表近实时 + 崩溃少丢数据）
    "checkpoint_seconds": 60,
    "focus_categories": ["dev"],
    "focus_merge_gap_seconds": 300,
    "focus_min_session_seconds": 900,
}


def load_config(root: Path = PROJECT_ROOT) -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    path = Path(root) / "config.json"
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            user = json.load(f)
        for key in DEFAULTS:
            if key in user:
                cfg[key] = user[key]
    return cfg


def db_path(cfg: Dict[str, Any], root: Path = PROJECT_ROOT) -> Path:
    p = Path(cfg["db_path"])
    return p if p.is_absolute() else Path(root) / p
