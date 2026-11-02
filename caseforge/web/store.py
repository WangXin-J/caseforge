"""SQLite 存储：执行记录。

每次执行一个 run，run 下面挂用例结果。
步骤明细用 JSON 存 —— 它只用于展示，不值得为它再拆一张表。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models import CaseResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT    NOT NULL,
    base_url    TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'running',
    total       INTEGER NOT NULL DEFAULT 0,
    passed      INTEGER NOT NULL DEFAULT 0,
    failed      INTEGER NOT NULL DEFAULT 0,
    duration_ms REAL    NOT NULL DEFAULT 0,
    error       TEXT
);

CREATE TABLE IF NOT EXISTS case_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    name          TEXT    NOT NULL,
    ok            INTEGER NOT NULL,
    duration_ms   REAL    NOT NULL,
    failure_types TEXT    NOT NULL,
    steps         TEXT    NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ---------- 写 ----------
    def create_run(self, base_url: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO runs (started_at, base_url) VALUES (?, ?)",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), base_url),
            )
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, results: list[CaseResult]) -> None:
        passed = sum(1 for r in results if r.ok)
        with self._connect() as conn:
            conn.execute("DELETE FROM case_results WHERE run_id = ?", (run_id,))
            for result in results:
                conn.execute(
                    "INSERT INTO case_results (run_id, name, ok, duration_ms, failure_types, steps) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        result.name,
                        1 if result.ok else 0,
                        round(result.duration_ms, 1),
                        json.dumps(result.failure_types, ensure_ascii=False),
                        json.dumps(
                            [
                                {
                                    "name": s.name,
                                    "ok": s.ok,
                                    "status": s.status,
                                    "elapsed_ms": round(s.elapsed_ms, 1),
                                    "failure_type": s.failure_type,
                                    "error": s.error,
                                }
                                for s in result.steps
                            ],
                            ensure_ascii=False,
                        ),
                    ),
                )
            conn.execute(
                "UPDATE runs SET status='completed', total=?, passed=?, failed=?, duration_ms=? WHERE id=?",
                (
                    len(results),
                    passed,
                    len(results) - passed,
                    round(sum(r.duration_ms for r in results), 1),
                    run_id,
                ),
            )

    def fail_run(self, run_id: int, error: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE runs SET status='failed', error=? WHERE id=?", (error, run_id))

    # ---------- 读 ----------
    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def get_cases(self, run_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM case_results WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        cases = []
        for row in rows:
            item = dict(row)
            item["failure_types"] = json.loads(item["failure_types"])
            item["steps"] = json.loads(item["steps"])
            cases.append(item)
        return cases

    def failure_summary(self, run_id: int) -> dict[str, int]:
        """按失败类型汇总，前端直接展示「这次挂了什么类型的问题」。"""
        counts: dict[str, int] = {}
        for case in self.get_cases(run_id):
            for kind in case["failure_types"]:
                counts[kind] = counts.get(kind, 0) + 1
        return counts
