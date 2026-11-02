"""Web 执行看板：跑用例、看历史、看失败归因。

服务端渲染 + 一点点原生 JS 轮询，不引入前端构建。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from ..loader import CaseFormatError, load_cases
from ..runner import run_suite
from .store import Store

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def create_app(db_path: str | Path = "report/caseforge.db", cases_path: str | Path = "examples/cases") -> FastAPI:
    store = Store(db_path)
    app = FastAPI(title="CaseForge", description="声明式接口用例执行引擎 · 执行看板", version="0.2.0")
    app.state.store = store
    app.state.cases_path = str(cases_path)

    def execute(run_id: int, base_url: str, workers: int) -> None:
        try:
            cases = load_cases(app.state.cases_path)
            results = run_suite(cases, base_url, workers=workers)
            store.finish_run(run_id, results)
        except Exception as exc:  # noqa: BLE001 - 后台任务必须兜住，否则 run 永远卡在 running
            store.fail_run(run_id, f"{type(exc).__name__}: {exc}")

    # ---------- 页面 ----------
    @app.get("/")
    def index(request: Request):
        return TEMPLATES.TemplateResponse(
            "index.html",
            {"request": request, "runs": store.list_runs(), "cases_path": app.state.cases_path},
        )

    @app.get("/runs/{run_id}")
    def run_detail(request: Request, run_id: int):
        run = store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="执行记录不存在")
        return TEMPLATES.TemplateResponse(
            "run.html",
            {
                "request": request,
                "run": run,
                "cases": store.get_cases(run_id),
                "failures": store.failure_summary(run_id),
            },
        )

    @app.post("/runs")
    def start_run_form(background: BackgroundTasks, base_url: str = Form(...), workers: int = Form(1)):
        run_id = store.create_run(base_url)
        background.add_task(execute, run_id, base_url, max(1, workers))
        return RedirectResponse(url=f"/runs/{run_id}", status_code=303)

    # ---------- JSON API ----------
    @app.post("/api/runs")
    def start_run(payload: dict, background: BackgroundTasks):
        base_url = (payload or {}).get("baseUrl")
        if not base_url:
            raise HTTPException(status_code=400, detail="baseUrl 必填")
        run_id = store.create_run(base_url)
        background.add_task(execute, run_id, base_url, int(payload.get("workers", 1)))
        return {"id": run_id, "status": "running"}

    @app.get("/api/runs")
    def list_runs(limit: int = 50):
        return {"items": store.list_runs(limit)}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: int):
        run = store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="执行记录不存在")
        return {
            "run": run,
            "cases": store.get_cases(run_id),
            "failureSummary": store.failure_summary(run_id),
        }

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app
