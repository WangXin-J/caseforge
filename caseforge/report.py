"""三种输出：控制台、JSON、JUnit XML。

JUnit XML 是刻意选的 —— Jenkins / GitLab CI / GitHub Actions 都能直接读，
不需要为「给 CI 看」再造一套格式。
"""
from __future__ import annotations

import json
from xml.sax.saxutils import escape, quoteattr

from .models import CaseResult

_RULE = "-" * 78


def summary(results: list[CaseResult]) -> dict:
    total = len(results)
    failed = [r for r in results if not r.ok]
    by_type: dict[str, int] = {}
    for r in failed:
        for t in r.failure_types or ["UNKNOWN_ERROR"]:
            by_type[t] = by_type.get(t, 0) + 1
    return {
        "total": total,
        "passed": total - len(failed),
        "failed": len(failed),
        "duration_ms": round(sum(r.duration_ms for r in results), 1),
        "failure_types": by_type,
    }


def to_console(results: list[CaseResult], verbose: bool = True) -> str:
    lines: list[str] = []
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        lines.append(f"[{mark}] {r.name}  ({r.duration_ms:.0f} ms)")
        if verbose:
            for s in r.steps:
                smark = "  ok  " if s.ok else "  x   "
                extra = f"  <{s.failure_type}>" if s.failure_type else ""
                lines.append(f"{smark}{s.name}  {s.status or '-'}  {s.elapsed_ms:.0f}ms{extra}")
                if not s.ok and s.error:
                    lines.append(f"       {s.error}")
                    if s.snippet:
                        lines.append(f"       response: {s.snippet[:160]}")

    stats = summary(results)
    lines.append(_RULE)
    lines.append(
        f"用例 {stats['total']}  通过 {stats['passed']}  失败 {stats['failed']}  "
        f"耗时 {stats['duration_ms'] / 1000:.2f}s"
    )
    if stats["failure_types"]:
        detail = ", ".join(f"{k}={v}" for k, v in sorted(stats["failure_types"].items()))
        lines.append(f"失败归因: {detail}")
    return "\n".join(lines)


def to_json(results: list[CaseResult]) -> str:
    return json.dumps(
        {
            "summary": summary(results),
            "cases": [
                {
                    "name": r.name,
                    "ok": r.ok,
                    "duration_ms": round(r.duration_ms, 1),
                    "tags": r.tags,
                    "steps": [
                        {
                            "name": s.name,
                            "ok": s.ok,
                            "status": s.status,
                            "elapsed_ms": round(s.elapsed_ms, 1),
                            "failure_type": s.failure_type,
                            "error": s.error,
                        }
                        for s in r.steps
                    ],
                }
                for r in results
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def to_junit(results: list[CaseResult]) -> str:
    total_failed = sum(1 for r in results if not r.ok)
    total_time = sum(r.duration_ms for r in results) / 1000
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<testsuites name="caseforge" tests="{len(results)}" failures="{total_failed}" time="{total_time:.3f}">',
    ]

    for r in results:
        failed_steps = [s for s in r.steps if not s.ok]
        out.append(
            f'  <testsuite name={quoteattr(r.name)} tests="{len(r.steps)}" '
            f'failures="{len(failed_steps)}" errors="0" time="{r.duration_ms / 1000:.3f}">'
        )
        for s in r.steps:
            out.append(
                f'    <testcase classname={quoteattr(r.name)} name={quoteattr(s.name)} '
                f'time="{s.elapsed_ms / 1000:.3f}">'
            )
            if not s.ok:
                message = f"[{s.failure_type}] {s.error or ''}"
                out.append(f"      <failure message={quoteattr(message)} type={quoteattr(s.failure_type or 'FAIL')}>")
                out.append(escape(s.error or ""))
                out.append("      </failure>")
            out.append("    </testcase>")
        out.append("  </testsuite>")

    out.append("</testsuites>")
    return "\n".join(out)
