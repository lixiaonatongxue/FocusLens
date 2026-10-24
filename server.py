"""本地 Web 报表服务。

隐私设计：
- 只绑定 127.0.0.1，不对外网/局域网开放；
- 页面静态资源（Vue/ECharts）全部本地化，打开报表不产生任何外部请求。

API：
  GET /api/meta                 版本、类别图例、隐私级别、专注类别
  GET /api/summary?date=...     某天明细（时间线/类别/Top/专注时段）
  GET /api/range?days=14        最近 N 天逐日汇总
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent import __version__
from agent.categories import legend
from agent.classifier import Classifier
from agent.config import db_path, load_config
from agent.report import parse_date, summarize_day, summarize_days
from agent.store import Store

ROOT = Path(__file__).resolve().parent
CFG = load_config(ROOT)
STORE = Store(db_path(CFG, ROOT))
CLASSIFIER = Classifier.load(ROOT / "rules" / "apps.json", ROOT / "rules" / "sites.json")
FOCUS_CFG = {
    k: CFG[k]
    for k in ("focus_categories", "focus_merge_gap_seconds", "focus_min_session_seconds")
}

app = FastAPI(title="FocusLens", version=__version__, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(ROOT / "web" / "static")), name="static")


@app.get("/")
def index():
    return FileResponse(str(ROOT / "web" / "index.html"))


@app.get("/api/meta")
def meta():
    return {
        "version": __version__,
        "categories": legend(),
        "privacy": CFG["privacy"],
        "idle_seconds": CFG["idle_seconds"],
        "focus_categories": CFG["focus_categories"],
    }


@app.get("/api/summary")
def summary(day: str = Query(default=None)):
    try:
        target = parse_date(day) if day else date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    return summarize_day(STORE, CLASSIFIER, target, FOCUS_CFG)


@app.get("/api/range")
def range_summary(days: int = Query(default=14, ge=1, le=90)):
    today = date.today()
    day_list = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    return {"days": summarize_days(STORE, CLASSIFIER, day_list, FOCUS_CFG)}
