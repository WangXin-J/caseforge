from __future__ import annotations

import pytest

from caseforge.loader import CaseFormatError, load_cases, load_case

GOOD = """
name: 基础用例
tags: [smoke]
vars:
  host: h1
steps:
  - name: 查询
    request:
      method: GET
      path: /api/health
    assert:
      - status: 200
      - header: { header: Content-Type, contains: json }
"""


def _write(tmp_path, text, name="case.yaml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_load_good_case(tmp_path):
    case = load_case(_write(tmp_path, GOOD))
    assert case.name == "基础用例"
    assert case.tags == ["smoke"]
    assert case.variables["host"] == "h1"
    assert len(case.steps) == 1
    kinds = [a.kind for a in case.steps[0].assertions]
    assert kinds == ["status", "header"]


def test_missing_name(tmp_path):
    with pytest.raises(CaseFormatError, match="缺少 name"):
        load_case(_write(tmp_path, "steps:\n  - name: a\n    request: {path: /x}\n"))


def test_empty_steps(tmp_path):
    with pytest.raises(CaseFormatError, match="steps"):
        load_case(_write(tmp_path, "name: x\nsteps: []\n"))


def test_missing_path(tmp_path):
    text = "name: x\nsteps:\n  - name: a\n    request:\n      method: GET\n"
    with pytest.raises(CaseFormatError, match="request.path"):
        load_case(_write(tmp_path, text))


def test_unknown_assertion(tmp_path):
    text = """
name: x
steps:
  - name: a
    request: { path: /x }
    assert:
      - magical: 1
"""
    with pytest.raises(CaseFormatError, match="未知断言类型"):
        load_case(_write(tmp_path, text))


def test_duplicate_step_name(tmp_path):
    text = """
name: x
steps:
  - name: same
    request: { path: /a }
  - name: same
    request: { path: /b }
"""
    with pytest.raises(CaseFormatError, match="重复"):
        load_case(_write(tmp_path, text))


def test_load_cases_from_dir(tmp_path):
    _write(tmp_path, GOOD, "a.yaml")
    _write(tmp_path, GOOD, "b.yaml")
    assert len(load_cases(tmp_path)) == 2


def test_broken_yaml(tmp_path):
    with pytest.raises(CaseFormatError, match="YAML"):
        load_case(_write(tmp_path, "name: [unclosed\n"))


def test_schema_assertion_is_wrapped(tmp_path):
    """回归用例：schema 断言本体是 JSON Schema，解析时必须包一层 {"schema": ...}。"""
    text = """
name: x
steps:
  - name: a
    request: { path: /x }
    assert:
      - schema: { type: object, required: [id] }
"""
    assertion = load_case(_write(tmp_path, text)).steps[0].assertions[0]
    assert assertion.kind == "schema"
    assert assertion.raw["schema"]["required"] == ["id"]


def test_json_path_requires_mapping(tmp_path):
    text = """
name: x
steps:
  - name: a
    request: { path: /x }
    assert:
      - json_path: not-a-mapping
"""
    with pytest.raises(CaseFormatError, match="json_path"):
        load_case(_write(tmp_path, text))
