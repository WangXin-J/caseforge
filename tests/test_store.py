from __future__ import annotations

from caseforge.models import CaseResult, StepResult
from caseforge.web.store import Store


def _result(name: str, ok: bool, failure_types: list[str] | None = None) -> CaseResult:
    step = StepResult(
        name="step-1",
        ok=ok,
        status=200 if ok else 500,
        elapsed_ms=12.0,
        failure_type=(failure_types or [None])[0],
        error=None if ok else "boom",
    )
    return CaseResult(name=name, ok=ok, steps=[step], duration_ms=12.0)


def test_create_and_finish_run(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    run_id = store.create_run("http://127.0.0.1:8010")

    run = store.get_run(run_id)
    assert run is not None
    assert run["status"] == "running"
    assert run["base_url"] == "http://127.0.0.1:8010"

    store.finish_run(run_id, [_result("a", True), _result("b", False, ["ASSERT_FAIL"])])
    run = store.get_run(run_id)
    assert run["status"] == "completed"
    assert run["total"] == 2
    assert run["passed"] == 1
    assert run["failed"] == 1


def test_cases_are_persisted_with_steps(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    run_id = store.create_run("http://127.0.0.1:8010")
    store.finish_run(run_id, [_result("用例甲", False, ["TIMEOUT"])])

    cases = store.get_cases(run_id)
    assert len(cases) == 1
    assert cases[0]["name"] == "用例甲"
    assert cases[0]["failure_types"] == ["TIMEOUT"]
    assert cases[0]["steps"][0]["failure_type"] == "TIMEOUT"


def test_failure_summary_counts_kinds(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    run_id = store.create_run("http://x")
    store.finish_run(
        run_id,
        [
            _result("a", False, ["ASSERT_FAIL"]),
            _result("b", False, ["ASSERT_FAIL"]),
            _result("c", False, ["TIMEOUT"]),
            _result("d", True),
        ],
    )
    assert store.failure_summary(run_id) == {"ASSERT_FAIL": 2, "TIMEOUT": 1}


def test_fail_run_records_error(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    run_id = store.create_run("http://x")
    store.fail_run(run_id, "CaseFormatError: 用例写错了")
    run = store.get_run(run_id)
    assert run["status"] == "failed"
    assert "用例写错了" in run["error"]


def test_list_runs_is_newest_first(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    first = store.create_run("http://a")
    second = store.create_run("http://b")
    ids = [r["id"] for r in store.list_runs()]
    assert ids == [second, first]


def test_missing_run_returns_none(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    assert store.get_run(999) is None
