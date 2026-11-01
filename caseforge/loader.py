"""YAML → 用例对象。

解析阶段只做结构校验，不做变量替换：变量依赖上一步的响应，必须等执行到那一步才知道。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Assertion, Case, Step

_ASSERTION_KINDS = ("status", "json_path", "schema", "header", "max_time")


class CaseFormatError(Exception):
    """用例文件写错时的报错，带上文件名和位置，避免「不知道哪个文件哪一行错了」。"""


def _fail(source: str, message: str) -> None:
    raise CaseFormatError(f"{source}: {message}")


def _parse_assertions(raw: Any, source: str) -> list[Assertion]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        _fail(source, "assert 必须是列表")

    result: list[Assertion] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or len(item) != 1:
            _fail(source, f"assert 第 {index + 1} 条格式错误，应为单键字典，例如 `- status: 200`")
        (kind, payload), = item.items()
        if kind not in _ASSERTION_KINDS:
            _fail(source, f"未知断言类型 {kind!r}，可用：{', '.join(_ASSERTION_KINDS)}")
        if kind in ("status", "header", "max_time"):
            if isinstance(payload, dict):
                payload = {"status": payload} if kind == "status" else payload
            raw_map = {"status": payload} if kind == "status" else (payload if isinstance(payload, dict) else {})
        else:
            raw_map = payload if isinstance(payload, dict) else {}
        result.append(Assertion(kind=kind, raw=raw_map))
    return result


def _parse_step(raw: dict, source: str, index: int) -> Step:
    if not isinstance(raw, dict):
        _fail(source, f"第 {index + 1} 个 step 必须是字典")

    request = raw.get("request") or {}
    if not isinstance(request, dict):
        _fail(source, f"step {index + 1} 的 request 必须是字典")

    method = str(request.get("method", "GET")).upper()
    path = request.get("path")
    if not path:
        _fail(source, f"step {index + 1} 缺少 request.path")

    return Step(
        name=str(raw.get("name") or f"step-{index + 1}"),
        method=method,
        path=str(path),
        json_body=request.get("json"),
        params=request.get("params"),
        headers=request.get("headers"),
        timeout=float(raw.get("timeout", request.get("timeout", 5.0))),
        extract=dict(raw.get("extract") or {}),
        assertions=_parse_assertions(raw.get("assert"), source),
        retries=int(raw.get("retries", 0)),
        continue_on_failure=bool(raw.get("continue_on_failure", False)),
    )


def load_case(path: str | Path) -> Case:
    path = Path(path)
    source = path.name
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CaseFormatError(f"{source}: YAML 解析失败 -> {exc}") from None

    if not isinstance(data, dict):
        _fail(source, "用例文件顶层必须是字典")

    name = data.get("name")
    if not name:
        _fail(source, "缺少 name")

    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        _fail(source, "steps 必须是非空列表")

    steps = [_parse_step(step, source, i) for i, step in enumerate(raw_steps)]

    names = [s.name for s in steps]
    if len(names) != len(set(names)):
        _fail(source, "step 名称重复，extract 会互相覆盖")

    return Case(
        name=str(name),
        steps=steps,
        variables=dict(data.get("vars") or {}),
        tags=list(data.get("tags") or []),
    )


def load_cases(target: str | Path) -> list[Case]:
    target = Path(target)
    if target.is_file():
        return [load_case(target)]
    if not target.is_dir():
        raise CaseFormatError(f"路径不存在: {target}")

    cases = [load_case(p) for p in sorted(target.rglob("*.yaml"))]
    if not cases:
        raise CaseFormatError(f"{target} 下没有找到 .yaml 用例")
    return cases
