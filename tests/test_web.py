from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from caseforge.web import create_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "db.sqlite", cases_path=ROOT / "examples" / "cases")
    return TestClient(app)


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_index_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "执行看板" in resp.text


def test_run_via_api_completes(client, base_url):
    resp = client.post("/api/runs", json={"baseUrl": base_url})
    assert resp.status_code == 200
    run_id = resp.json()["id"]

    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["run"]["status"] == "completed"
    assert detail["run"]["total"] == 2
    assert detail["run"]["passed"] == 2
    assert detail["run"]["failed"] == 0
    assert detail["failureSummary"] == {}


def test_run_detail_page_renders(client, base_url):
    run_id = client.post("/api/runs", json={"baseUrl": base_url}).json()["id"]
    page = client.get(f"/runs/{run_id}")
    assert page.status_code == 200
    assert "告警规则" in page.text


def test_form_submission_redirects(client, base_url):
    resp = client.post("/runs", data={"base_url": base_url, "workers": 2}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/runs/")


def test_missing_base_url_is_rejected(client):
    assert client.post("/api/runs", json={}).status_code == 400


def test_unknown_run_is_404(client):
    assert client.get("/api/runs/9999").status_code == 404
    assert client.get("/runs/9999").status_code == 404


def test_failures_are_summarized(client):
    """全部用例打到一个不存在的地址，应该全部失败，并且归因是连接错误。"""
    run_id = client.post("/api/runs", json={"baseUrl": "http://127.0.0.1:1"}).json()["id"]
    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["run"]["failed"] == 2
    assert detail["failureSummary"].get("CONNECTION_ERROR") == 2


def test_index_lists_previous_runs(client, base_url):
    client.post("/api/runs", json={"baseUrl": base_url})
    page = client.get("/")
    assert "http://127.0.0.1" in page.text
