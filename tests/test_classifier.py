"""分类引擎测试：全部使用合成的进程名/标题字符串，不涉及任何真实数据。"""

import unittest
from pathlib import Path

from agent.classifier import Classifier

RULES_DIR = Path(__file__).resolve().parents[1] / "rules"


class ClassifierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = Classifier.load(RULES_DIR / "apps.json", RULES_DIR / "sites.json")

    def test_exe_rule_case_insensitive(self):
        self.assertEqual(self.c.classify("WeChat.exe").category, "im")
        self.assertEqual(self.c.classify("wechat.exe").category, "im")
        self.assertEqual(self.c.classify("WeChat.exe").name, "微信")

    def test_dev_tools(self):
        for exe in ("Code.exe", "idea64.exe", "pycharm64.exe", "WindowsTerminal.exe"):
            self.assertEqual(self.c.classify(exe).category, "dev", exe)

    def test_browser_site_classification(self):
        r = self.c.classify("chrome.exe", "某个视频 - 哔哩哔哩 (゜-゜)つロ 干杯~")
        self.assertEqual((r.category, r.name), ("browse-fun", "哔哩哔哩"))

        r = self.c.classify("msedge.exe", "focuslens/focuslens: 本地屏幕时间 - GitHub")
        self.assertEqual((r.category, r.name), ("browse-dev", "GitHub"))

        r = self.c.classify("chrome.exe", "一个没有任何规则的普通网页")
        self.assertEqual((r.category, r.name), ("browser", "Chrome"))

    def test_site_alias_bilibili_uppercase(self):
        r = self.c.classify("360se.exe", "标题里有大写 Bilibili 字样")
        self.assertEqual((r.category, r.name), ("browse-fun", "哔哩哔哩"))

    def test_title_rule_for_unknown_host(self):
        r = self.c.classify("SomeUWPHost.exe", "微信")
        self.assertEqual(r.category, "im")

    def test_uwp_host_falls_back_to_title(self):
        r = self.c.classify("ApplicationFrameHost.exe", "计算器")
        self.assertEqual((r.category, r.name), ("tool", "计算器"))
        r = self.c.classify("ApplicationFrameHost.exe", "完全没见过的标题")
        self.assertEqual(r.category, "other")

    def test_lockscreen_is_idle(self):
        self.assertEqual(self.c.classify("LogonUI.exe").category, "idle")

    def test_unknown_falls_back_other(self):
        r = self.c.classify("StrangeApp.exe")
        self.assertEqual((r.category, r.name), ("other", "StrangeApp.exe"))

    def test_site_rules_do_not_leak_to_non_browser(self):
        # 非浏览器进程即使标题带 B 站关键词，也不走 sites.json
        r = self.c.classify("SomeEditor.exe", "哔哩哔哩")
        self.assertEqual(r.category, "other")

    def test_rules_file_is_valid_and_ordered(self):
        import json

        for name in ("apps.json", "sites.json"):
            data = json.loads((RULES_DIR / name).read_text(encoding="utf-8"))
            self.assertIsInstance(data, list)
            self.assertGreater(len(data), 20, name)
            for rule in data:
                self.assertIn("category", rule, name)
                self.assertIn("match", rule, name)


if __name__ == "__main__":
    unittest.main()
