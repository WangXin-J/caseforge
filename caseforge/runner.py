"""执行器。

一条用例 = 一串步骤，步骤之间靠 extract 传递变量。
失败不立即中断整轮（可继续跑其它用例），但要记录失败类型，供报告归因。
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests

from .assertions import AssertionFailure, evaluate
from .jsonpath import query
from .models import Assertion, Case, CaseResult, Step, StepResult

_VAR = re.compile(r"\$\{\{\s*([A-Za-z0-9_][A-Za-z0-9_.\-]*)\s*\}\}")
_EXACT_VAR = re.compile(r"^\$\{\{\s*([A-Za-z0-9_][A-Za-z0-9_.\-]*)\s*\}\}$")


class VariableMissing(KeyError):
    pass


def interpolate(value: Any, context: dict[str, Any]) -> Any:
    """把 `${{ name }}` 替换成上下文里的值。

    - 整个字符串只有一个占位符时，返回原始类型（不把数字变成字符串）
    - 混合文本时按字符串拼接
    - 不做表达式求值：用例里出现计算逻辑，说明设计有问题
    """
    if isinstance(value, str):
        exact = _EXACT_VAR.match(value)
        if exact:
            key = exact.group(1)
            if key not in context:
                raise VariableMissing(f"变量未定义: ${{{{ {key} }}}}，当前可用: {sorted(context)}")
            return context[key]

        def repl(match: re.Match) -> str:
            key = match.group(1)
            if key not in context:
                raise VariableMissing(f"变量未定义: ${{{{ {key} }}}}，当前可用: {sorted(context)}")
            return str(context[key])

        return _VAR.sub(repl, value)
    if isinstance(value, dict):
        return {k: interpolate(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate(v, context) for v in value]
    return value


def _classify(exc: Exception, status: int | None) -> str:
    """失败归因。

    这是这个工具和「跑脚本」的区别：报告里要能一眼看出是服务挂了、契约变了，
    还是用例写错了。
    """
    if isinstance(exc, AssertionFailure):
        # 5xx 时即使断言写的是状态码，也归到服务端问题，避免把锅甩给用例
        return "SERVER_ERROR" if status and status >= 500 else exc.assertion_type
    if isinstance(exc, requests.Timeout):
        return "TIMEOUT"
    if isinstance(exc, requests.ConnectionError):
        return "CONNECTION_ERROR"
    if isinstance(exc, VariableMissing):
        return "CASE_ERROR"
    return "UNKNOWN_ERROR"


def _run_step(step: Step, base_url: str, context: dict[str, Any], session: requests.Session) -> StepResult:
    started = time.perf_counter()
    result = StepResult(name=step.name, ok=False)

    try:
        path = interpolate(step.path, context)
        url = base_url.rstrip("/") + ("" if path.startswith("/") else "/") + path

        attempt = 0
        while True:
            attempt += 1
            try:
                response = session.request(
                    step.method,
                    url,
                    json=interpolate(step.json_body, context),
                    params=interpolate(step.params, context),
                    headers=interpolate(step.headers, context),
                    timeout=step.timeout,
                )
                break
            except (requests.Timeout, requests.ConnectionError):
                if attempt > step.retries:
                    raise
                time.sleep(0.2 * attempt)

        result.status = response.status_code
        result.snippet = (response.text or "").replace("\n", " ")[:200]

        for assertion in step.assertions:
            resolved = Assertion(kind=assertion.kind, raw=interpolate(assertion.raw, context))
            evaluate(resolved, response, (time.perf_counter() - started) * 1000)

        for var_name, expr in step.extract.items():
            context[var_name] = query(response.json(), expr)
            result.extracted[var_name] = context[var_name]

        result.ok = True
    except Exception as exc:  # noqa: BLE001 - 执行器必须兜住所有异常，否则一条用例会带崩整轮
        result.error = f"{type(exc).__name__}: {exc}"
        result.failure_type = _classify(exc, result.status)
    finally:
        result.elapsed_ms = (time.perf_counter() - started) * 1000

    return result


def run_case(case: Case, base_url: str, env: dict[str, Any] | None = None) -> CaseResult:
    context: dict[str, Any] = {"timestamp": int(time.time() * 1000)}
    context.update(env or {})
    # vars 内部允许引用 vars，按书写顺序解析（后写的可以引用先写的）
    for key, value in case.variables.items():
        context[key] = interpolate(value, context)

    started = time.perf_counter()
    step_results: list[StepResult] = []

    with requests.Session() as session:
        session.headers.setdefault("Accept", "application/json")
        for step in case.steps:
            step_result = _run_step(step, base_url, context, session)
            step_results.append(step_result)
            if not step_result.ok and not step.continue_on_failure:
                break

    ok = all(s.ok for s in step_results) and len(step_results) == len(case.steps)
    return CaseResult(
        name=case.name,
        ok=ok,
        steps=step_results,
        duration_ms=(time.perf_counter() - started) * 1000,
        tags=case.tags,
    )


def run_suite(
    cases: list[Case],
    base_url: str,
    env: dict[str, Any] | None = None,
    workers: int = 1,
) -> list[CaseResult]:
    """并发执行。每个用例独占一个 session，避免 cookie 互相污染。"""
    if workers <= 1:
        return [run_case(c, base_url, env) for c in cases]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda c: run_case(c, base_url, env), cases))
