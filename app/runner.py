from __future__ import annotations
import asyncio
import json
import os
import signal
import shlex
from datetime import datetime, timezone

import aiosqlite

from app.database import claim_next_queued_run, get_run, requeue_run, update_run
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
    cmd: list[str],
    cwd: str,
) -> None:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
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


async def reattach_running_runs(db: aiosqlite.Connection) -> list[asyncio.Task[None]]:
    from app.database import list_runs
    monitor_tasks: list[asyncio.Task[None]] = []
    running = await list_runs(db, status=RunStatus.running)
    for row in running:
        pid = row.get("pid")
        if pid and is_pid_alive(pid):
            monitor_tasks.append(asyncio.create_task(_monitor_existing(db, row["id"], pid)))
        else:
            await requeue_run(db, row["id"])
    return monitor_tasks


async def _monitor_existing(db: aiosqlite.Connection, run_id: str, pid: int) -> None:
    while is_pid_alive(pid):
        await asyncio.sleep(5)
    await update_run(db, run_id, status=RunStatus.failed, finished_at=_now())


class QueueWorker:
    def __init__(
        self,
        db: aiosqlite.Connection,
        max_concurrent_runs: int,
        recovered_tasks: list[asyncio.Task[None]] | None = None,
    ) -> None:
        self.db = db
        self.max_concurrent_runs = max_concurrent_runs
        self.recovered_tasks = recovered_tasks or []
        self._wake_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    def notify(self) -> None:
        self._wake_event.set()

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        active: set[asyncio.Task[None]] = set(self.recovered_tasks)
        try:
            while True:
                while len(active) < self.max_concurrent_runs:
                    row = await claim_next_queued_run(self.db)
                    if row is None:
                        break
                    active.add(asyncio.create_task(self._execute(row)))

                if active:
                    done, active = await asyncio.wait(
                        active, return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        task.result()
                else:
                    self._wake_event.clear()
                    await self._wake_event.wait()
        finally:
            for task in active:
                task.cancel()

    async def _execute(self, row: dict[str, object]) -> None:
        try:
            command_json = row.get("command_json")
            command = json.loads(command_json) if command_json else shlex.split(str(row["command"]))
            await launch_run(
                db=self.db,
                run_id=str(row["id"]),
                cmd=command,
                cwd=str(row["run_dir"]),
            )
        except Exception:
            attempts = int(row.get("launch_attempts") or 0)
            if attempts < 3:
                await requeue_run(self.db, str(row["id"]))
                self.notify()
            else:
                await update_run(
                    self.db,
                    str(row["id"]),
                    status=RunStatus.failed,
                    finished_at=_now(),
                )
