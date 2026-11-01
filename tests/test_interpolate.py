from __future__ import annotations

import pytest

from caseforge.runner import VariableMissing, interpolate


def test_plain_string():
    assert interpolate("abc", {}) == "abc"


def test_simple_substitution():
    assert interpolate("id-${{ n }}", {"n": 5}) == "id-5"


def test_whitespace_tolerant():
    assert interpolate("${{n}}", {"n": "x"}) == "x"
    assert interpolate("${{   n   }}", {"n": "x"}) == "x"


def test_nested_structures():
    data = {"a": ["${{ n }}", {"b": "${{ n }}"}]}
    assert interpolate(data, {"n": 1}) == {"a": ["1", {"b": "1"}]}


def test_missing_variable_raises():
    with pytest.raises(VariableMissing) as info:
        interpolate("${{ nope }}", {"n": 1})
    assert "nope" in str(info.value)
    assert "可用" in str(info.value)


def test_non_string_untouched():
    assert interpolate(42, {}) == 42
    assert interpolate(None, {}) is None
    assert interpolate(True, {}) is True
