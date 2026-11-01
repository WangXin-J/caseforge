"""用例模型。

用 dataclass 而不是 dict，是为了让「用例长什么样」有一处明确答案：
loader 负责把 YAML 变成这些对象，runner 只认这些对象。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Assertion:
    """一条断言。kind 决定用哪种比较方式，raw 保留原始配置便于报错时回显。"""

    kind: str
    raw: dict

    def describe(self) -> str:
        if self.kind == "status":
            return f"status == {self.raw['status']}"
        if self.kind == "json_path":
            return f"json_path {self.raw.get('path')}"
        if self.kind == "schema":
            return f"schema {self.raw.get('schema')}"
        return self.kind


@dataclass
class Step:
    name: str
    method: str
    path: str
    json_body: Any = None
    params: dict | None = None
    headers: dict | None = None
    timeout: float = 5.0
    extract: dict[str, str] = field(default_factory=dict)
    assertions: list[Assertion] = field(default_factory=list)
    retries: int = 0
    continue_on_failure: bool = False


@dataclass
class Case:
    name: str
    steps: list[Step]
    variables: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


@dataclass
class StepResult:
    name: str
    ok: bool
    status: int | None = None
    elapsed_ms: float = 0.0
    error: str | None = None
    failure_type: str | None = None
    snippet: str = ""
    extracted: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseResult:
    name: str
    ok: bool
    steps: list[StepResult]
    duration_ms: float = 0.0
    tags: list[str] = field(default_factory=list)

    @property
    def failure_types(self) -> list[str]:
        return [s.failure_type for s in self.steps if s.failure_type]
