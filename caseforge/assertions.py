"""断言求值。

每条断言失败都会抛 AssertionFailure，带上「哪条断言、期望什么、实际什么」。
这是报告可读性的前提 —— 只说 AssertionError 的报告，等于没报告。
"""
from __future__ import annotations

from typing import Any

from .jsonpath import PathNotFound, query
from .models import Assertion


class AssertionFailure(Exception):
    def __init__(self, assertion_type: str, message: str):
        super().__init__(message)
        self.assertion_type = assertion_type


def _fmt(value: Any, limit: int = 120) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "..."


def evaluate(assertion: Assertion, response, elapsed_ms: float) -> None:
    kind = assertion.kind
    if kind == "status":
        _check_status(assertion, response)
    elif kind == "json_path":
        _check_json_path(assertion, response)
    elif kind == "schema":
        _check_schema(assertion, response)
    elif kind == "header":
        _check_header(assertion, response)
    elif kind == "max_time":
        limit = float(assertion.raw["max_time_ms"])
        if elapsed_ms > limit:
            raise AssertionFailure("ASSERT_FAIL", f"响应耗时 {elapsed_ms:.0f}ms 超过上限 {limit:.0f}ms")
    else:
        raise AssertionFailure("ASSERT_FAIL", f"未知断言类型: {kind}")


def _check_status(assertion: Assertion, response) -> None:
    expected = assertion.raw["status"]
    allowed = expected if isinstance(expected, list) else [expected]
    if response.status_code not in allowed:
        raise AssertionFailure(
            "ASSERT_FAIL",
            f"状态码不符：期望 {allowed}，实际 {response.status_code}，响应体 {_fmt(response.text)}",
        )


def _check_json_path(assertion: Assertion, response) -> None:
    expr = assertion.raw["path"]
    try:
        actual = query(response.json(), expr)
    except PathNotFound:
        raise AssertionFailure("SCHEMA_DRIFT", f"响应中找不到路径 {expr}，实际响应 {_fmt(response.text)}") from None
    except ValueError as exc:
        raise AssertionFailure("ASSERT_FAIL", str(exc)) from None

    raw = assertion.raw
    if "equals" in raw and actual != raw["equals"]:
        raise AssertionFailure("ASSERT_FAIL", f"{expr} 期望 {_fmt(raw['equals'])}，实际 {_fmt(actual)}")
    if "contains" in raw and raw["contains"] not in (actual if isinstance(actual, list) else [actual]):
        raise AssertionFailure("ASSERT_FAIL", f"{expr} 期望包含 {_fmt(raw['contains'])}，实际 {_fmt(actual)}")
    if "gt" in raw and not (isinstance(actual, (int, float)) and actual > raw["gt"]):
        raise AssertionFailure("ASSERT_FAIL", f"{expr} 期望 > {raw['gt']}，实际 {_fmt(actual)}")
    if "lt" in raw and not (isinstance(actual, (int, float)) and actual < raw["lt"]):
        raise AssertionFailure("ASSERT_FAIL", f"{expr} 期望 < {raw['lt']}，实际 {_fmt(actual)}")
    if "exists" in raw and bool(actual) != bool(raw["exists"]):
        raise AssertionFailure("ASSERT_FAIL", f"{expr} 存在性不符：期望 exists={raw['exists']}，实际 {_fmt(actual)}")


def _check_schema(assertion: Assertion, response) -> None:
    try:
        import jsonschema
    except ImportError:
        raise AssertionFailure("ASSERT_FAIL", "schema 断言需要 jsonschema，请先 pip install jsonschema") from None

    schema = assertion.raw["schema"]
    try:
        jsonschema.validate(instance=response.json(), schema=schema)
    except jsonschema.ValidationError as exc:
        raise AssertionFailure("SCHEMA_DRIFT", f"响应结构不符合契约：{exc.message}") from None


def _check_header(assertion: Assertion, response) -> None:
    name = assertion.raw["header"]
    actual = response.headers.get(name, "")
    expected = assertion.raw.get("contains")
    if expected is None and not actual:
        raise AssertionFailure("ASSERT_FAIL", f"缺少响应头 {name}")
    if expected is not None and expected not in actual:
        raise AssertionFailure("ASSERT_FAIL", f"响应头 {name} 期望包含 {expected!r}，实际 {actual!r}")
