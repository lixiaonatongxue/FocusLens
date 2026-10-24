# FocusLens

> "Screen Time" for Windows — automatically track how much time you spend in each app. **100% local, zero network requests.**

[中文](README.md) | **English**

![FocusLens daily report](docs/screenshot-today.png)

The iPhone has Screen Time; Windows never got an equivalent. RescueTime is a cloud subscription, and existing open-source options recognize Chinese apps and websites poorly — FocusLens aims to fill that gap:

- **Privacy first**: runs fully locally, makes zero network requests, and your data can be wiped with one command — open source, so these claims are verifiable;
- **Chinese rule library out of the box**: WeChat / QQ / DingTalk / NetEase Cloud Music / Bilibili / Zhihu / JD… correctly categorized from the moment you install it; the rule library accepts community PRs;
- **Readable daily report**: 24-hour timeline, category breakdown, top apps, and focus-session stats;
- **Lightweight**: the collector uses only the Python standard library (Win32 APIs via ctypes) — no third-party dependencies.

## Privacy (read this first)

- **Zero network requests**: the collector imports no networking library, and the Vue/ECharts assets for the web report are vendored into this repository, so opening the page never contacts any CDN. Search the code to verify.
- Only the **foreground window's** process name and title are read — information any desktop application can query. No keylogging, no screenshots, no uploads.
- Three privacy levels (the `privacy` key in `config.json`):

  | Level | Behavior |
  |---|---|
  | `default` | store process name + category only; **window titles are never written to disk** |
  | `hash` | store only a hash of the title (distinguishes documents but can't be read back) |
  | `full` | store titles (locally only) |

- All data lives in a single SQLite file (`data/focuslens.db`); `python run.py clear --yes` wipes it and reclaims disk space.
- The web report binds to `127.0.0.1` only — it is never exposed to your LAN.
- ⚠️ This is a time tracker *for yourself*. Do not install it on someone else's computer.

## Quick start

Requirements: Windows 10/11, Python 3.9+ (only the web report needs `fastapi`/`uvicorn`; **the collector has zero third-party dependencies**).

```bash
git clone https://github.com/lixiaonatongxue/FocusLens.git
cd FocusLens
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt

# 1) Start collecting (runs until Ctrl+C; try 60 seconds first with --duration 60)
.venv/Scripts/python.exe run.py collect

# 2) View reports
.venv/Scripts/python.exe run.py report today     # CLI
.venv/Scripts/python.exe run.py serve            # Web → http://127.0.0.1:8810

# 3) (Recommended) configure once — collection starts automatically at every logon
.venv/Scripts/python.exe run.py autostart

# No data yet and want a preview?
.venv/Scripts/python.exe run.py demo             # seeds a fictional "day of a developer"
```

Other commands:

| Command | What it does |
|---|---|
| `run.py autostart` | auto-start at logon (installs a per-user startup entry and launches immediately); `--remove` stops and uninstalls |
| `run.py report week` | last 7 days as a text report |
| `run.py report today --date 2026-10-24` | view a specific date |
| `run.py classify --exe WeChat.exe` | debug rule matching (use it when contributing rules) |
| `run.py clear --yes` | wipe all local data |

## How it works

```
foreground events (SetWinEventHook) ──┐
                                      ├─→ collector state machine ─→ classifier ─→ SQLite
1s polling fallback + idle detection ─┘   (exe rules + browser-title subdivision)
```

- **Collection**: event-driven window-switch hook plus a 1-second polling fallback; title changes (such as browser tab switches) also split sessions; a session is checkpointed to disk every 60 seconds so the report stays near real-time;
- **Idle detection**: no keyboard/mouse input for 5 minutes (configurable) marks you as "away", with the first 5 minutes of grace credited to the current app;
- **Sleep guard**: large sampling gaps (sleep/hibernate) close the current segment, so sleep time is never attributed to any app;
- **Browser subdivision**: Chrome/Edge window titles contain the page name ("xxx - Bilibili"); `rules/sites.json` subdivides browser time down to the site level.

## Contribute a rule (PRs welcome — the bar is one line of JSON)

```json
{"match": {"exe": ["Weixin.exe"]}, "category": "im", "name": "WeChat"}
```

Verify it with `python run.py classify --exe Weixin.exe`, then submit. See [CONTRIBUTING.md](CONTRIBUTING.md) (Chinese) for details.

## Roadmap

- [x] v0.1 collection / classification / SQLite / CLI report / local web report / auto-start at logon
- [ ] v0.2 shareable daily-card image export, "slacking" alerts
- [ ] v0.3 tray icon, UWP app identification (`GetApplicationUserModelId`), CSV export

## Development

```bash
.venv/Scripts/python.exe -m unittest discover -s tests -t .
```

Design notes: [docs/design-plan.md](docs/design-plan.md) (Chinese).

## License

[MIT](LICENSE)
