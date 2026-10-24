"""自动启动模块测试：启动器只写进临时目录，不碰真实 Startup 文件夹。"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from agent import autostart as auto


class AutostartTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_install_writes_vbs_with_absolute_paths(self):
        root = Path("D:/some/focuslens")
        vbs = auto.install(root, startup_dir=self.tmp)
        self.assertTrue(vbs.exists())
        text = vbs.read_text(encoding="ascii")
        self.assertIn("collect --quiet", text)
        self.assertIn(str(root / "run.py"), text)
        self.assertIn(str(root), text)

    def test_install_is_idempotent(self):
        auto.install(Path("D:/a"), startup_dir=self.tmp)
        vbs = auto.install(Path("D:/b"), startup_dir=self.tmp)
        self.assertIn("D:\\b", vbs.read_text(encoding="ascii"))

    def test_uninstall(self):
        auto.install(Path("D:/a"), startup_dir=self.tmp)
        self.assertTrue(auto.uninstall(self.tmp))
        self.assertFalse(auto.launcher_path(self.tmp).exists())
        self.assertFalse(auto.uninstall(self.tmp))

    def test_pid_alive(self):
        self.assertTrue(auto.pid_alive(os.getpid()))
        self.assertFalse(auto.pid_alive(None))
        self.assertFalse(auto.pid_alive(0))
        self.assertFalse(auto.pid_alive(-1))
        self.assertFalse(auto.pid_alive(4_000_000))  # 不存在的 PID

    def test_pidfile_roundtrip_and_running(self):
        self.assertIsNone(auto.collector_running(self.tmp))
        auto.write_pid(self.tmp, 12345)
        self.assertEqual(auto.read_pid(self.tmp), 12345)
        self.assertIsNone(auto.collector_running(self.tmp))  # 12345 不是活进程
        auto.write_pid(self.tmp, os.getpid())
        self.assertEqual(auto.collector_running(self.tmp), os.getpid())
        auto.clear_pid(self.tmp)
        self.assertIsNone(auto.read_pid(self.tmp))

    def test_stop_collector_without_process(self):
        auto.write_pid(self.tmp, 4_000_000)
        self.assertFalse(auto.stop_collector(self.tmp))
        self.assertIsNone(auto.read_pid(self.tmp))  # 残留 pid 文件被清理


if __name__ == "__main__":
    unittest.main()
