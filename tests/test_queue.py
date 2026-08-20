import asyncio

import aiosqlite
import pytest

from app.database import get_run, init_db, insert_run
from app.models import RunStatus
from app.runner import QueueWorker


@pytest.mark.asyncio
async def test_queue_worker_limits_concurrency(tmp_path, monkeypatch):
    active = 0
    peak = 0
    release = asyncio.Event()

    async def fake_launch(db, run_id, cmd, cwd):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await release.wait()
        active -= 1

    monkeypatch.setattr("app.runner.launch_run", fake_launch)
    async with aiosqlite.connect(tmp_path / "runs.db") as db:
        await init_db(db)
        for index in range(3):
            await insert_run(db, f"run-{index}", {}, "nextflow", f"/runs/{index}", f"2026-01-01T00:00:0{index}Z")

        worker = QueueWorker(db, max_concurrent_runs=2)
        worker.start()
        for _ in range(20):
            if active == 2:
                break
            await asyncio.sleep(0.01)
        release.set()
        await worker.stop()

    assert peak == 2


@pytest.mark.asyncio
async def test_queue_worker_marks_run_failed_after_three_launch_attempts(tmp_path, monkeypatch):
    async def failing_launch(db, run_id, cmd, cwd):
        raise RuntimeError("Nextflow unavailable")

    monkeypatch.setattr("app.runner.launch_run", failing_launch)
    async with aiosqlite.connect(tmp_path / "runs.db") as db:
        await init_db(db)
        await insert_run(db, "run-1", {}, "nextflow", "/runs/1", "2026-01-01T00:00:00Z")

        worker = QueueWorker(db, max_concurrent_runs=1)
        worker.start()
        for _ in range(100):
            row = await get_run(db, "run-1")
            if row["status"] == RunStatus.failed:
                break
            await asyncio.sleep(0.01)
        await worker.stop()

    assert row["status"] == RunStatus.failed
    assert row["launch_attempts"] == 3