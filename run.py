"""FocusLens 命令行入口。

用法：
  python run.py collect [--duration 秒]     采集（默认一直运行，Ctrl+C 停止）
  python run.py autostart [--remove]        开机自动采集：安装/立即启动/卸载
  python run.py classify --exe X [--title Y] 调试规则匹配（贡献规则时用）
  python run.py report [today|week]          文本报表
  python run.py serve [--port N]             本地 Web 报表（默认 127.0.0.1:8810）
  python run.py demo [--force]               写入一天合成演示数据
  python run.py clear --yes                  清空全部本地记录
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agent.config import db_path, load_config  # noqa: E402
from agent.store import Store  # noqa: E402


def _classifier():
    from agent.classifier import Classifier

    return Classifier.load(ROOT / "rules" / "apps.json", ROOT / "rules" / "sites.json")


def _fmt_dur(sec) -> str:
    sec = int(sec)
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m" if h else (f"{m}m{s:02d}s" if m else f"{s}s")


def cmd_collect(args, cfg):
    from agent import autostart as auto
    from agent.collector import Collector

    if args.duration is not None and args.duration <= 0:
        sys.exit("--duration 需要正数（秒）")
    data_dir = db_path(cfg).parent
    running = auto.collector_running(data_dir)
    if running:
        sys.exit(f"采集器已在运行（PID {running}）。停止：python run.py autostart --remove")
    auto.write_pid(data_dir, os.getpid())

    store = Store(db_path(cfg))
    classifier = _classifier()
    counter = {"n": 0}

    def on_event(ev):
        counter["n"] += 1
        clock = time.strftime("%H:%M:%S", time.localtime(ev["end"]))
        print(f"[{clock}] {ev['name'] or ev['exe']} · {_fmt_dur(ev['duration'])} · {ev['category']}")

    collector = Collector(
        store,
        classifier,
        idle_seconds=cfg["idle_seconds"],
        poll_interval=cfg["poll_interval"],
        privacy=cfg["privacy"],
        checkpoint_seconds=cfg.get("checkpoint_seconds", 60),
        on_event=None if args.quiet else on_event,
    )
    if not args.quiet:
        print(
            f"FocusLens 采集启动  privacy={cfg['privacy']}  空闲阈值={cfg['idle_seconds']}s\n"
            f"数据落盘 → {db_path(cfg)}"
        )
        if args.duration:
            print(f"限时运行 {args.duration:.0f} 秒后自动停止")
    try:
        collector.run_forever(args.duration, quiet=args.quiet)
    finally:
        store.close()
        auto.clear_pid(data_dir)
        if not args.quiet:
            print(f"\n本次共记录 {counter['n']} 段。运行 `python run.py report today` 查看。")


def cmd_autostart(args, cfg):
    from agent import autostart as auto

    data_dir = db_path(cfg).parent
    if args.remove:
        stopped = auto.stop_collector(data_dir)
        removed = auto.uninstall()
        print(
            ("已停止后台采集；" if stopped else "后台采集未在运行；")
            + ("已删除开机启动项。" if removed else "未发现开机启动项。")
        )
        return
    vbs = auto.install(ROOT)
    print(f"开机启动项已安装 → {vbs}")
    running = auto.collector_running(data_dir)
    if running:
        print(f"采集器已在后台运行（PID {running}）。")
    else:
        pid = auto.launch_collector_now(ROOT, data_dir)
        print(f"已启动后台采集（无窗口，PID {pid}），日志 → {data_dir / 'collector.log'}")
    print("之后每次开机登录都会自动开始采集；停止并卸载：python run.py autostart --remove")


def cmd_classify(args, cfg):
    classifier = _classifier()
    r = classifier.classify(args.exe, args.title or "")
    print(f"exe={args.exe!r} title={args.title!r}\n→ category={r.category}  name={r.name}")


def cmd_report(args, cfg):
    from agent import report

    try:
        day = report.parse_date(args.date) if args.date else None
    except ValueError:
        sys.exit("日期格式应为 YYYY-MM-DD，例如 --date 2026-10-24")
    store = Store(db_path(cfg))
    try:
        if args.what == "week":
            text = report.render_week(store, _classifier())
        else:
            text = report.render_day(store, _classifier(), day)
    finally:
        store.close()
    print(text)


def cmd_serve(args, cfg):
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        sys.exit("缺少依赖：请先运行 .venv/Scripts/python.exe -m pip install fastapi uvicorn")
    from server import app

    port = args.port or cfg["port"]
    print(f"FocusLens Web 报表：http://127.0.0.1:{port}（只绑定本机回环地址）")
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def cmd_demo(args, cfg):
    from agent.demo import seed_demo

    store = Store(db_path(cfg))
    try:
        n = seed_demo(store, _classifier(), force=args.force)
    finally:
        store.close()
    print(f"已写入 {n} 段演示数据。运行 `python run.py serve` 后打开网页查看，"
          f"或 `python run.py report today`。")


def cmd_clear(args, cfg):
    if not args.yes:
        sys.exit("清空操作不可恢复，请加 --yes 确认：python run.py clear --yes")
    store = Store(db_path(cfg))
    try:
        n = store.delete_all()
    finally:
        store.close()
    print(f"已清空 {n} 条记录（VACUUM 已回收磁盘空间）。")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="focuslens", description="FocusLens 焦点时间统计器")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("collect", help="采集前台应用使用时间")
    p.add_argument("--duration", type=float, default=None, help="限时运行秒数（测试用）")
    p.add_argument("--quiet", action="store_true", help="静默模式（后台运行用）")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("autostart", help="开机自动采集（一次配置）")
    p.add_argument("--remove", action="store_true", help="停止后台采集并删除开机启动项")
    p.set_defaults(func=cmd_autostart)

    p = sub.add_parser("classify", help="调试规则匹配")
    p.add_argument("--exe", required=True)
    p.add_argument("--title", default="")
    p.set_defaults(func=cmd_classify)

    p = sub.add_parser("report", help="文本报表")
    p.add_argument("what", nargs="?", default="today", choices=["today", "week"])
    p.add_argument("--date", default=None, help="YYYY-MM-DD，默认今天")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("serve", help="本地 Web 报表")
    p.add_argument("--port", type=int, default=None)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("demo", help="写入一天合成演示数据")
    p.add_argument("--force", action="store_true", help="库非空也写入")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("clear", help="清空全部本地记录")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_clear)

    args = parser.parse_args(argv)
    cfg = load_config(ROOT)
    args.func(args, cfg)


if __name__ == "__main__":
    main()
