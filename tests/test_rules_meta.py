"""规则文件与类别注册表的一致性检查（防患于未然的静态测试）。"""

import json
import unittest
from pathlib import Path

from agent.categories import CATEGORIES

RULES_DIR = Path(__file__).resolve().parents[1] / "rules"


class RulesMetaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.apps = json.loads((RULES_DIR / "apps.json").read_text(encoding="utf-8"))
        cls.sites = json.loads((RULES_DIR / "sites.json").read_text(encoding="utf-8"))

    def test_every_category_is_registered(self):
        for name, rules in (("apps.json", self.apps), ("sites.json", self.sites)):
            for rule in rules:
                self.assertIn(
                    rule.get("category"),
                    CATEGORIES,
                    f"{name} 引用了未注册类别: {rule}",
                )

    def test_no_duplicate_exe_across_rules(self):
        seen = {}
        for rule in self.apps:
            for exe in rule.get("match", {}).get("exe", []):
                key = exe.lower()
                self.assertNotIn(
                    key, seen, f"进程 {exe} 在多条规则中出现（后写的会被遮蔽）"
                )
                seen[key] = rule["category"]

    def test_site_rules_match_title(self):
        for rule in self.sites:
            titles = rule.get("match", {}).get("title", [])
            self.assertTrue(titles, f"sites 规则缺少 title 关键词: {rule}")
            for kw in titles:
                self.assertIsInstance(kw, str) and self.assertTrue(kw.strip())

    def test_rule_names_present(self):
        for name, rules in (("apps.json", self.apps), ("sites.json", self.sites)):
            for rule in rules:
                if "name" in rule:
                    self.assertIsInstance(rule["name"], str)
                    self.assertTrue(rule["name"].strip(), f"{name} 空显示名: {rule}")


if __name__ == "__main__":
    unittest.main()
