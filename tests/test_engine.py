from __future__ import annotations

from pathlib import Path

import pytest

from caseforge.loader import load_cases
from caseforge.models import Assertion, Case, Step
from caseforge.runner import run_case, run_suite

ROOT = Path(__file__).resolve().parents[1]


def _case(*steps: Step) -> Case:
    return Case(name="临时用例", steps=list(steps))


def test_example_cases_all_pass(base_url):
    """仓库里自带的示例用例必须全绿 —— 否则说明示例和引擎已经脱节。"""
    results = run_suite(load_cases(ROOT / "examples" / "cases"), base_url)
    failures = [
        (r.name, s.name, s.failure_type, s.error)
        for r in results
        for s in r.steps
        if not s.ok
    ]
    assert not failures, failures


def test_extract_chains_between_steps(base_url):
    case = load_cases(ROOT / "examples" / "cases" / "alert_rules.yaml")[0]
    result = run_case(case, base_url)
    assert result.ok, [s.error for s in result.steps if s.error]
    extracted = result.steps[0].extracted
    assert "rule_id" in extracted and extracted["rule_id"].startswith("r-")


def test_server_error_is_classified(base_url):
    step = Step(name="触发 5xx", method="GET", path="/api/boom",
                assertions=[Assertion("status", {"status": 200})])
    result = run_case(_case(step), base_url)
    assert not result.ok
    assert result.steps[0].failure_type == "SERVER_ERROR"


def test_timeout_is_classified(base_url):
    step = Step(name="慢接口", method="GET", path="/api/slow?ms=800", timeout=0.2)
    result = run_case(_case(step), base_url)
    assert not result.ok
    assert result.steps[0].failure_type == "TIMEOUT"


def test_connection_error_is_classified():
    step = Step(name="连不上", method="GET", path="/api/health", timeout=0.5)
    result = run_case(_case(step), "http://127.0.0.1:1")
    assert not result.ok
    assert result.steps[0].failure_type == "CONNECTION_ERROR"


def test_missing_variable_is_case_error(base_url):
    step = Step(name="引用了不存在的变量", method="GET", path="/api/alert/rules/${{ nope }}")
    result = run_case(_case(step), base_url)
    assert not result.ok
    assert result.steps[0].failure_type == "CASE_ERROR"


def test_failure_stops_following_steps(base_url):
    first = Step(name="第一步必失败", method="GET", path="/api/boom",
                 assertions=[Assertion("status", {"status": 200})])
    second = Step(name="不该被执行", method="GET", path="/api/health")
    result = run_case(_case(first, second), base_url)
    assert not result.ok
    assert len(result.steps) == 1


def test_continue_on_failure(base_url):
    first = Step(name="失败但继续", method="GET", path="/api/boom",
                 assertions=[Assertion("status", {"status": 200})],
                 continue_on_failure=True)
    second = Step(name="仍然执行", method="GET", path="/api/health",
                  assertions=[Assertion("status", {"status": 200})])
    result = run_case(_case(first, second), base_url)
    assert not result.ok
    assert len(result.steps) == 2
    assert result.steps[1].ok


def test_concurrent_run_keeps_results_isolated(base_url):
    cases = load_cases(ROOT / "examples" / "cases")
    results = run_suite(cases, base_url, workers=4)
    assert len(results) == len(cases)
    assert all(r.ok for r in results)
