import asyncio
import pytest
import aiosqlite
from unittest.mock import AsyncMock, patch, MagicMock
from app.database import init_db, insert_run, get_run
from app.models import RunStatus
from app.runner import launch_run, cancel_run, is_pid_alive


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.mark.asyncio
async def test_is_pid_alive_current_process():
    import os
    assert is_pid_alive(os.getpid()) is True


@pytest.mark.asyncio
async def test_is_pid_alive_nonexistent():
    assert is_pid_alive(9999999) is False


@pytest.mark.asyncio
async def test_launch_run_sets_running_status(db_path, tmp_path):
    work_dir = str(tmp_path / "work")
    async with aiosqlite.connect(db_path) as db:
        await init_db(db)
        await insert_run(db, run_id="run-1", params={"input": "x", "outdir": "/out"}, created_at="2026-01-01T00:00:00Z")

        mock_proc = AsyncMock()
        mock_proc.pid = 42
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0

        with patch("app.runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            await launch_run(
                db=db,
                run_id="run-1",
                params={"input": "x", "outdir": "/out"},
                pipeline_path="/pipeline/main.nf",
                work_dir=work_dir,
                nextflow_bin="nextflow",
            )

        row = await get_run(db, "run-1")
    assert row["status"] == RunStatus.completed


@pytest.mark.asyncio
async def test_launch_run_sets_failed_on_nonzero_exit(db_path, tmp_path):
    work_dir = str(tmp_path / "work")
    async with aiosqlite.connect(db_path) as db:
        await init_db(db)
        await insert_run(db, run_id="run-2", params={}, created_at="2026-01-01T00:00:00Z")

        mock_proc = AsyncMock()
        mock_proc.pid = 99
        mock_proc.wait = AsyncMock(return_value=1)
        mock_proc.returncode = 1

        with patch("app.runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            await launch_run(
                db=db,
                run_id="run-2",
                params={},
                pipeline_path="/pipeline/main.nf",
                work_dir=work_dir,
                nextflow_bin="nextflow",
            )

        row = await get_run(db, "run-2")
    assert row["status"] == RunStatus.failed
    assert row["exit_code"] == 1


@pytest.mark.asyncio
async def test_cancel_run_sends_sigterm(db_path):
    async with aiosqlite.connect(db_path) as db:
        await init_db(db)
        await insert_run(db, run_id="run-3", params={}, created_at="2026-01-01T00:00:00Z")
        from app.database import update_run
        await update_run(db, "run-3", status=RunStatus.running, pid=12345)

        with patch("app.runner.os.kill") as mock_kill:
            result = await cancel_run(db, "run-3")
            mock_kill.assert_any_call(12345, 15)

        row = await get_run(db, "run-3")
    assert result is True
    assert row["status"] == RunStatus.cancelled
