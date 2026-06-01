from __future__ import annotations
import asyncio
import os
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from app.database import get_run, update_run
from app.models import RunStatus


def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def launch_run(
    db: aiosqlite.Connection,
    run_id: str,
    params: dict[str, Any],
    pipeline_path: str,
    run_dir: str,
    nextflow_bin: str,
) -> None:
    run_work_dir = Path(run_dir) / run_id / "work"
    run_work_dir.mkdir(parents=True, exist_ok=True)
    log_path =  Path(run_dir) / run_id / "nextflow.log"
    outdir = Path(run_dir) / run_id / "results"

    cmd = [nextflow_bin, "-log", str(log_path),"run", pipeline_path, "-profile", "test,docker", "-work-dir", str(run_work_dir)]
    for key, value in params.items():
        cmd += [f"--{key}", str(value)]
    cmd += ["--outdir", str(outdir)]


    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
    )

    await update_run(db, run_id, status=RunStatus.running, pid=proc.pid, started_at=_now())

    exit_code = await proc.wait()
    finished_at = _now()

    if exit_code == 0:
        await update_run(db, run_id, status=RunStatus.completed, finished_at=finished_at, exit_code=0)
    else:
        await update_run(db, run_id, status=RunStatus.failed, finished_at=finished_at, exit_code=exit_code)


async def cancel_run(db: aiosqlite.Connection, run_id: str) -> bool:
    row = await get_run(db, run_id)
    if row is None or row["status"] != RunStatus.running:
        return False
    pid = row["pid"]
    if pid and is_pid_alive(pid):
        os.kill(pid, signal.SIGTERM)
    await update_run(db, run_id, status=RunStatus.cancelled, finished_at=_now())
    return True


async def reattach_running_runs(db: aiosqlite.Connection) -> None:
    from app.database import list_runs
    running = await list_runs(db, status=RunStatus.running)
    for row in running:
        pid = row.get("pid")
        if pid and is_pid_alive(pid):
            asyncio.create_task(_monitor_existing(db, row["id"], pid))
        else:
            await update_run(
                db,
                row["id"],
                status=RunStatus.failed,
                finished_at=_now(),
            )


async def _monitor_existing(db: aiosqlite.Connection, run_id: str, pid: int) -> None:
    while is_pid_alive(pid):
        await asyncio.sleep(5)
    await update_run(db, run_id, status=RunStatus.failed, finished_at=_now())
