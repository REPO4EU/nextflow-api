from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any, Optional
import aiosqlite
from app.models import RunStatus

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS runs (
    id            TEXT PRIMARY KEY,
    status        TEXT NOT NULL DEFAULT 'queued',
    params        TEXT NOT NULL DEFAULT '{}',
    command       TEXT,
    run_dir       TEXT,
    pid           INTEGER,
    created_at    TEXT NOT NULL,
    started_at    TEXT,
    finished_at   TEXT,
    exit_code     INTEGER,
    user_id       TEXT NOT NULL DEFAULT '',
    workflow_name TEXT,
    command_json  TEXT,
    launch_attempts INTEGER NOT NULL DEFAULT 0
)
"""


async def init_db(db: aiosqlite.Connection) -> None:
    await db.execute(CREATE_TABLE)
    await _ensure_schema_columns(db)
    await db.commit()


async def _ensure_schema_columns(db: aiosqlite.Connection) -> None:
    async with db.execute("PRAGMA table_info(runs)") as cursor:
        rows = await cursor.fetchall()
    columns = [row[1] for row in rows]
    if "user_id" not in columns:
        await db.execute("ALTER TABLE runs ADD COLUMN user_id TEXT")
    if "workflow_name" not in columns:
        await db.execute("ALTER TABLE runs ADD COLUMN workflow_name TEXT")
    if "command_json" not in columns:
        await db.execute("ALTER TABLE runs ADD COLUMN command_json TEXT")
    if "launch_attempts" not in columns:
        await db.execute("ALTER TABLE runs ADD COLUMN launch_attempts INTEGER NOT NULL DEFAULT 0")


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
    user_id: str = "",
    workflow_name: Optional[str] = None,
    command_json: Optional[str] = None,
) -> str:
    await db.execute(
        "INSERT INTO runs (id, status, params, command, run_dir, created_at, user_id, workflow_name, command_json) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?)",
        (run_id, json.dumps(params), command, run_dir, created_at, user_id, workflow_name, command_json),
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

    query = query.replace("SELECT * FROM runs", """SELECT runs.*,
        CASE WHEN runs.status = 'queued' THEN (
            SELECT COUNT(*) FROM runs AS queued
            WHERE queued.status = 'queued'
              AND queued.user_id = runs.user_id
              AND (queued.created_at < runs.created_at
                   OR (queued.created_at = runs.created_at AND queued.id <= runs.id))
        ) ELSE NULL END AS queue_position
        FROM runs""")
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


async def claim_next_queued_run(db: aiosqlite.Connection) -> Optional[dict[str, Any]]:
    """Atomically reserve the oldest queued run for a worker slot."""
    db.row_factory = aiosqlite.Row
    await db.execute("BEGIN IMMEDIATE")
    try:
        async with db.execute(
            "SELECT * FROM runs WHERE status = 'queued' ORDER BY created_at ASC, id ASC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            await db.commit()
            return None
        await db.execute(
            "UPDATE runs SET status = 'running', started_at = ?, launch_attempts = launch_attempts + 1 WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), row["id"]),
        )
        await db.commit()
        row = dict(row)
        row["status"] = RunStatus.running
        row["launch_attempts"] = row.get("launch_attempts", 0) + 1
        return row
    except Exception:
        await db.rollback()
        raise


async def requeue_stale_running_runs(db: aiosqlite.Connection) -> None:
    await db.execute(
        "UPDATE runs SET status = 'queued', pid = NULL, started_at = NULL WHERE status = 'running'"
    )
    await db.commit()


async def requeue_run(db: aiosqlite.Connection, run_id: str) -> None:
    await db.execute(
        "UPDATE runs SET status = 'queued', pid = NULL, started_at = NULL WHERE id = ?",
        (run_id,),
    )
    await db.commit()


async def cancel_queued_run(db: aiosqlite.Connection, run_id: str, finished_at: str) -> bool:
    cursor = await db.execute(
        "UPDATE runs SET status = 'cancelled', finished_at = ? WHERE id = ? AND status = 'queued'",
        (finished_at, run_id),
    )
    await db.commit()
    return cursor.rowcount == 1


async def delete_run(db: aiosqlite.Connection, run_id: str) -> None:
    await db.execute("DELETE FROM runs WHERE id = ?", (run_id,))
    await db.commit()
