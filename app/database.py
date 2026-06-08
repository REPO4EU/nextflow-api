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
    started_at TEXT,
    finished_at TEXT,
    exit_code   INTEGER,
    user_id     TEXT NOT NULL DEFAULT ''
)
"""


async def init_db(db: aiosqlite.Connection) -> None:
    await db.execute(CREATE_TABLE)
    await _ensure_user_id_column(db)
    await db.commit()


async def _ensure_user_id_column(db: aiosqlite.Connection) -> None:
    async with db.execute("PRAGMA table_info(runs)") as cursor:
        rows = await cursor.fetchall()
    columns = [row[1] for row in rows]
    if "user_id" not in columns:
        await db.execute("ALTER TABLE runs ADD COLUMN user_id TEXT")


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
    user_id: str,
) -> str:
    await db.execute(
        "INSERT INTO runs (id, status, params, command, run_dir, created_at, user_id) VALUES (?, 'queued', ?, ?, ?, ?, ?)",
        (run_id, json.dumps(params), command, run_dir, created_at, user_id),
    )
    await db.commit()
    return run_id


async def get_run(
    db: aiosqlite.Connection,
    run_id: str,
    user_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    db.row_factory = aiosqlite.Row
    query = "SELECT * FROM runs WHERE id = ?"
    args: list[Any] = [run_id]
    if user_id is not None:
        query += " AND user_id = ?"
        args.append(user_id)
    async with db.execute(query, tuple(args)) as cursor:
        row = await cursor.fetchone()
    return _row_to_dict(row) if row else None


async def list_runs(
    db: aiosqlite.Connection,
    status: Optional[RunStatus],
    user_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    db.row_factory = aiosqlite.Row
    query = "SELECT * FROM runs"
    args: list[Any] = []

    if user_id is not None:
        query += " WHERE user_id = ?"
        args.append(user_id)

    if status is not None:
        query += " AND" if args else " WHERE"
        query += " status = ?"
        args.append(status.value)

    query += " ORDER BY created_at DESC"
    async with db.execute(query, tuple(args)) as cursor:
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
