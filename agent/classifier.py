"""规则分类引擎：进程名精确匹配 + 浏览器标题网站级细分。

规则文件为 JSON 数组，单条形如：
    {"match": {"exe": ["Code.exe"]}, "category": "dev", "name": "VS Code"}
    {"match": {"title": ["哔哩哔哩", "bilibili"]}, "category": "browse-fun", "name": "哔哩哔哩"}

匹配规则（按顺序）：
1. apps.json 里仅含 exe 条件的规则 → 进程名精确匹配（不分大小写）；
2. 若命中的是浏览器（category == "browser"），先用 sites.json 的标题关键词
   细分到网站级；匹配不到归入“浏览器”；
3. apps.json 里含 title 条件的规则（用于 UWP 宿主/未知进程靠标题识别）；
4. 兜底 other。

同一文件内规则自上而下匹配，先命中者优先——把更具体的关键词放前面。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Sequence, Set, Tuple


class Result(NamedTuple):
    category: str
    name: str


class Classifier:
    def __init__(self, app_rules: Sequence[dict], site_rules: Sequence[dict]):
        self._exe_map: Dict[str, Result] = {}
        # (允许的 exe 集合或 None, [(关键词, category, name)])
        self._app_title_rules: List[Tuple[Optional[Set[str]], list]] = []
        self._site_rules: List[Tuple[Optional[Set[str]], list]] = []
        for rule in app_rules:
            self._compile(rule, self._app_title_rules, allow_exe_map=True)
        for rule in site_rules:
            self._compile(rule, self._site_rules, allow_exe_map=False)

    # -- 装配 -----------------------------------------------------------

    def _compile(self, rule: dict, bucket: list, allow_exe_map: bool) -> None:
        match = rule.get("match") or {}
        category = rule.get("category", "other")
        name = rule.get("name")
        exes = {str(e).lower() for e in match.get("exe", [])}
        titles = [str(t).lower() for t in match.get("title", [])]
        if not exes and not titles:
            return
        if exes and not titles and allow_exe_map:
            for exe in exes:
                self._exe_map[exe] = Result(category, name or "")
            return
        tokens = [(kw, category, name or kw) for kw in titles]
        bucket.append((exes or None, tokens))

    @classmethod
    def load(cls, apps_path: Path, sites_path: Path) -> "Classifier":
        return cls(_read_rules(apps_path), _read_rules(sites_path))

    # -- 推理 -----------------------------------------------------------

    def classify(self, exe: str, title: str = "") -> Result:
        exe_l = (exe or "").lower()
        title_l = (title or "").lower()

        title_hit = self._match(self._app_title_rules, exe_l, title_l)
        exe_hit = self._exe_map.get(exe_l)

        if exe_hit is not None:
            if exe_hit.category == "browser" and title_l:
                site = self._match(self._site_rules, exe_l, title_l)
                if site is not None:
                    return site
                return Result("browser", exe_hit.name or exe)
            if exe_hit.category == "other" and title_hit is not None:
                # UWP 宿主等：exe 只能给出“未知”，标题能给出身份
                return title_hit
            return Result(exe_hit.category, exe_hit.name or exe)

        if title_hit is not None:
            return title_hit
        return Result("other", exe or "未知应用")

    @staticmethod
    def _match(rules, exe_l: str, title_l: str) -> Optional[Result]:
        if not title_l:
            return None
        for exes, tokens in rules:
            if exes is not None and exe_l not in exes:
                continue
            for kw, category, name in tokens:
                if kw in title_l:
                    return Result(category, name)
        return None

    @property
    def browser_exes(self) -> Set[str]:
        return {exe for exe, r in self._exe_map.items() if r.category == "browser"}


def _read_rules(path: Path) -> List[dict]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):  # 兼容 {"rules": [...]} 包装
        data = data.get("rules", [])
    return [r for r in data if isinstance(r, dict)]
