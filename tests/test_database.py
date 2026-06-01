import asyncio
import pytest
import aiosqlite
from app.database import init_db, insert_run, get_run, list_runs, update_run
from app.models import RunStatus


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.mark.asyncio
async def test_insert_and_get_run(db_path):
    async with aiosqlite.connect(db_path) as db:
        await init_db(db)
        run_id = await insert_run(db, run_id="run-1", params={"input": "x"}, created_at="2026-01-01T00:00:00Z")
        row = await get_run(db, "run-1")
    assert row["id"] == "run-1"
    assert row["status"] == RunStatus.queued
    assert row["params"] == {"input": "x"}


@pytest.mark.asyncio
async def test_update_run_status(db_path):
    async with aiosqlite.connect(db_path) as db:
        await init_db(db)
        await insert_run(db, run_id="run-2", params={}, created_at="2026-01-01T00:00:00Z")
        await update_run(db, "run-2", status=RunStatus.running, pid=12345, started_at="2026-01-01T00:00:01Z")
        row = await get_run(db, "run-2")
    assert row["status"] == RunStatus.running
    assert row["pid"] == 12345


@pytest.mark.asyncio
async def test_list_runs_filter(db_path):
    async with aiosqlite.connect(db_path) as db:
        await init_db(db)
        await insert_run(db, run_id="r1", params={}, created_at="2026-01-01T00:00:00Z")
        await insert_run(db, run_id="r2", params={}, created_at="2026-01-01T00:00:01Z")
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
