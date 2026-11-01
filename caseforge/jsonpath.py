"""极简 JSONPath 求值。

只实现用例真正需要的子集：`$.a.b`、`$.a[0].b`、`$.items[*].id`。
自己写而不是引依赖，是因为这点逻辑不值得多一个包，也方便报错时给出原表达式。
"""
from __future__ import annotations

import re
from typing import Any

_TOKEN = re.compile(r"\[\*\]|\[(\d+)\]|\.([A-Za-z0-9_]+)")


class PathNotFound(KeyError):
    def __init__(self, expr: str):
        super().__init__(f"路径不存在: {expr}")


def query(data: Any, expr: str) -> Any:
    if expr == "$":
        return data
    if not expr.startswith("$"):
        raise ValueError(f"JSONPath 必须以 $ 开头: {expr}")

    nodes = [data]
    matched = False
    for m in _TOKEN.finditer(expr):
        matched = True
        wildcard, index, key = m.group(0) == "[*]", m.group(1), m.group(2)
        nxt = []
        for node in nodes:
            if wildcard:
                if isinstance(node, list):
                    nxt.extend(node)
            elif index is not None:
                if isinstance(node, list) and int(index) < len(node):
                    nxt.append(node[int(index)])
            elif key is not None:
                if isinstance(node, dict) and key in node:
                    nxt.append(node[key])
        nodes = nxt

    if not matched:
        raise ValueError(f"无法解析的 JSONPath: {expr}")
    if not nodes and "[*]" not in expr:
        raise PathNotFound(expr)
    return nodes[0] if len(nodes) == 1 and "[*]" not in expr else nodes
