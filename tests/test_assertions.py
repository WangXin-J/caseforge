from __future__ import annotations

import json

import pytest

from caseforge.assertions import AssertionFailure, evaluate
from caseforge.models import Assertion


class FakeResponse:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.headers = headers or {"Content-Type": "application/json; charset=utf-8"}
        self.text = json.dumps(self._payload, ensure_ascii=False)

    def json(self):
        return self._payload


def test_status_pass():
    evaluate(Assertion("status", {"status": 200}), FakeResponse(200), 10)


def test_status_fail_message_contains_actual():
    with pytest.raises(AssertionFailure) as info:
        evaluate(Assertion("status", {"status": 201}), FakeResponse(400), 10)
    assert "400" in str(info.value)
    assert info.value.assertion_type == "ASSERT_FAIL"


def test_json_path_equals():
    response = FakeResponse(payload={"enabled": True})
    evaluate(Assertion("json_path", {"path": "$.enabled", "equals": True}), response, 5)


def test_json_path_missing_is_schema_drift():
    with pytest.raises(AssertionFailure) as info:
        evaluate(Assertion("json_path", {"path": "$.nope", "equals": 1}), FakeResponse(), 5)
    assert info.value.assertion_type == "SCHEMA_DRIFT"


def test_json_path_numeric_compare():
    response = FakeResponse(payload={"cpu": 12.5})
    evaluate(Assertion("json_path", {"path": "$.cpu", "gt": 0}), response, 5)
    evaluate(Assertion("json_path", {"path": "$.cpu", "lt": 100}), response, 5)
    with pytest.raises(AssertionFailure):
        evaluate(Assertion("json_path", {"path": "$.cpu", "gt": 50}), response, 5)


def test_json_path_contains_on_list():
    response = FakeResponse(payload={"items": [{"id": "a"}, {"id": "b"}]})
    evaluate(Assertion("json_path", {"path": "$.items[*].id", "contains": "b"}), response, 5)
    with pytest.raises(AssertionFailure):
        evaluate(Assertion("json_path", {"path": "$.items[*].id", "contains": "z"}), response, 5)


def test_schema_violation_is_schema_drift():
    schema = {"type": "object", "required": ["id"]}
    with pytest.raises(AssertionFailure) as info:
        evaluate(Assertion("schema", {"schema": schema}), FakeResponse(payload={"x": 1}), 5)
    assert info.value.assertion_type == "SCHEMA_DRIFT"


def test_schema_pass():
    schema = {"type": "object", "required": ["id"]}
    evaluate(Assertion("schema", {"schema": schema}), FakeResponse(payload={"id": "r-1"}), 5)


def test_max_time():
    evaluate(Assertion("max_time", {"max_time_ms": 500}), FakeResponse(), 100)
    with pytest.raises(AssertionFailure) as info:
        evaluate(Assertion("max_time", {"max_time_ms": 500}), FakeResponse(), 800)
    assert "超过上限" in str(info.value)


def test_header_contains():
    response = FakeResponse(headers={"Content-Type": "application/json; charset=utf-8"})
    evaluate(Assertion("header", {"header": "Content-Type", "contains": "json"}), response, 5)
    with pytest.raises(AssertionFailure):
        evaluate(Assertion("header", {"header": "Content-Type", "contains": "xml"}), response, 5)
