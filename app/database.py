from __future__ import annotations
import json
from typing import Any, Optional
import aiosqlite
from app.models import RunStatus

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    status      TEXT NOT NULL DEFAULT 'queued',
    params      TEXT NOT NULL DEFAULT '{}',
    command     TEXT,
    run_dir     TEXT,
    pid         INTEGER,
    created_at  TEXT NOT NULL,
    started_at  TEXT,
    finished_at TEXT,
    exit_code   INTEGER
)
"""


async def init_db(db: aiosqlite.Connection) -> None:
    await db.execute(CREATE_TABLE)
    await db.commit()


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    d = dict(row)
    d["params"] = json.loads(d["params"])
    d["status"] = RunStatus(d["status"])
    return d


async def insert_run(
    db: aiosqlite.Connection,
    run_id: str,
    params: dict[str, Any],
    command: str,
    run_dir: str,
    created_at: str,
) -> str:
    await db.execute(
        "INSERT INTO runs (id, status, params, command, run_dir, created_at) VALUES (?, 'queued', ?, ?, ?, ?)",
        (run_id, json.dumps(params), command, run_dir, created_at),
    )
    await db.commit()
    return run_id


async def get_run(db: aiosqlite.Connection, run_id: str) -> Optional[dict[str, Any]]:
    db.row_factory = aiosqlite.Row
    async with db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)) as cursor:
        row = await cursor.fetchone()
    return _row_to_dict(row) if row else None


async def list_runs(
    db: aiosqlite.Connection,
    status: Optional[RunStatus],
) -> list[dict[str, Any]]:
    db.row_factory = aiosqlite.Row
    if status is None:
        async with db.execute("SELECT * FROM runs ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
    else:
        async with db.execute(
            "SELECT * FROM runs WHERE status = ? ORDER BY created_at DESC",
            (status.value,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def update_run(
    db: aiosqlite.Connection,
    run_id: str,
    status: Optional[RunStatus] = None,
    pid: Optional[int] = None,
    started_at: Optional[str] = None,
    finished_at: Optional[str] = None,
    exit_code: Optional[int] = None,
) -> None:
    fields: list[str] = []
    values: list[Any] = []
    if status is not None:
        fields.append("status = ?")
        values.append(status.value)
    if pid is not None:
        fields.append("pid = ?")
        values.append(pid)
    if started_at is not None:
        fields.append("started_at = ?")
        values.append(started_at)
    if finished_at is not None:
        fields.append("finished_at = ?")
        values.append(finished_at)
    if exit_code is not None:
        fields.append("exit_code = ?")
        values.append(exit_code)
    if not fields:
        return
    values.append(run_id)
    await db.execute(f"UPDATE runs SET {', '.join(fields)} WHERE id = ?", values)
    await db.commit()
