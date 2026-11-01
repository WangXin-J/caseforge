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


def test_exact_placeholder_preserves_type():
    """整串只有一个占位符时保留原始类型，否则 `equals: 90` 会拿字符串和数字比。"""
    assert interpolate("${{ n }}", {"n": 90}) == 90
    assert interpolate("${{ flag }}", {"flag": True}) is True
    assert interpolate("${{ obj }}", {"obj": {"a": 1}}) == {"a": 1}
    # 混在文本里时按字符串拼接
    assert interpolate("n=${{ n }}", {"n": 90}) == "n=90"
