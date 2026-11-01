from __future__ import annotations

import pytest

from caseforge.jsonpath import PathNotFound, query


def test_simple_key():
    assert query({"id": "r-1"}, "$.id") == "r-1"


def test_nested_key():
    assert query({"a": {"b": {"c": 3}}}, "$.a.b.c") == 3


def test_index():
    assert query({"items": [{"id": "a"}, {"id": "b"}]}, "$.items[1].id") == "b"


def test_wildcard():
    data = {"items": [{"id": "a"}, {"id": "b"}]}
    assert query(data, "$.items[*].id") == ["a", "b"]


def test_root():
    assert query({"x": 1}, "$") == {"x": 1}


def test_missing_key_raises():
    with pytest.raises(PathNotFound):
        query({"a": 1}, "$.b")


def test_index_out_of_range_raises():
    with pytest.raises(PathNotFound):
        query({"items": []}, "$.items[0]")


def test_bad_expression():
    with pytest.raises(ValueError):
        query({}, "a.b")
