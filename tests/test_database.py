import asyncio
import pytest
import aiosqlite
from app.database import cancel_queued_run, claim_next_queued_run, init_db, insert_run, get_run, list_runs, update_run
from app.models import RunStatus


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.mark.asyncio
async def test_insert_and_get_run(db_path):
    async with aiosqlite.connect(db_path) as db:
        await init_db(db)
        run_id = await insert_run(db, run_id="run-1", params={"input": "x"}, command="nextflow run pipeline", run_dir="/runs/run-1", created_at="2026-01-01T00:00:00Z")
        row = await get_run(db, "run-1")
    assert row["id"] == "run-1"
    assert row["status"] == RunStatus.queued
    assert row["params"] == {"input": "x"}


@pytest.mark.asyncio
async def test_update_run_status(db_path):
    async with aiosqlite.connect(db_path) as db:
        await init_db(db)
        await insert_run(db, run_id="run-2", params={}, command="nextflow run pipeline", run_dir="/runs/run-2", created_at="2026-01-01T00:00:00Z")
        await update_run(db, "run-2", status=RunStatus.running, pid=12345, started_at="2026-01-01T00:00:01Z")
        row = await get_run(db, "run-2")
    assert row["status"] == RunStatus.running
    assert row["pid"] == 12345


@pytest.mark.asyncio
async def test_list_runs_filter(db_path):
    async with aiosqlite.connect(db_path) as db:
        await init_db(db)
        await insert_run(db, run_id="r1", params={}, command="nextflow run pipeline", run_dir="/runs/r1", created_at="2026-01-01T00:00:00Z")
        await insert_run(db, run_id="r2", params={}, command="nextflow run pipeline", run_dir="/runs/r2", created_at="2026-01-01T00:00:01Z")
        await update_run(db, "r2", status=RunStatus.completed)
        all_runs = await list_runs(db, status=None)
        completed = await list_runs(db, status=RunStatus.completed)
    assert len(all_runs) == 2
    assert len(completed) == 1
    assert completed[0]["id"] == "r2"


@pytest.mark.asyncio
async def test_get_run_not_found(db_path):
    async with aiosqlite.connect(db_path) as db:
        await init_db(db)
        row = await get_run(db, "nonexistent")
    assert row is None


@pytest.mark.asyncio
async def test_claim_next_run_is_fifo_and_reports_user_queue_positions(db_path):
    async with aiosqlite.connect(db_path) as db:
        await init_db(db)
        await insert_run(db, "r1", {}, "nextflow run one", "/runs/r1", "2026-01-01T00:00:00Z", user_id="alice")
        await insert_run(db, "r2", {}, "nextflow run two", "/runs/r2", "2026-01-01T00:00:01Z", user_id="alice")
        await insert_run(db, "r3", {}, "nextflow run three", "/runs/r3", "2026-01-01T00:00:02Z", user_id="bob")

        rows = await list_runs(db, status=None, user_id="alice")
        claimed = await claim_next_queued_run(db)
        remaining = await list_runs(db, status=None, user_id="alice")

    assert [row["queue_position"] for row in rows] == [2, 1]
    assert claimed["id"] == "r1"
    assert remaining[0]["queue_position"] == 1


@pytest.mark.asyncio
async def test_cancel_queued_run_does_not_cancel_claimed_run(db_path):
    async with aiosqlite.connect(db_path) as db:
        await init_db(db)
        await insert_run(db, "r1", {}, "nextflow run one", "/runs/r1", "2026-01-01T00:00:00Z")
        await claim_next_queued_run(db)
        cancelled = await cancel_queued_run(db, "r1", "2026-01-01T00:00:01Z")
        row = await get_run(db, "r1")

    assert cancelled is False
    assert row["status"] == RunStatus.running
