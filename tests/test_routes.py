import json
import os
import pytest
import aiosqlite
from pathlib import Path
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from app.database import update_run
from app.models import RunStatus


@pytest.fixture
async def client(tmp_path):
    """Provide a test client with temp DB and work dir."""
    import app.config as cfg
    data_dir = Path(os.environ.get("DATA_DIR", str(tmp_path)))
    run_root = data_dir / "pytest-runs"
    run_root.mkdir(parents=True, exist_ok=True)

    cfg.DB_PATH = str(run_root / "test.db")
    cfg.RUN_DIR = str(run_root)
    cfg.NEXTFLOW_BIN = "nextflow"

    from app.main import app, lifespan as app_lifespan

    with patch("app.main.shutil.which", return_value="/usr/bin/nextflow"):
        async with app_lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                yield c


@pytest.mark.asyncio
async def test_submit_run_returns_202(client):
    with patch("app.routes.runs.launch_run", new_callable=AsyncMock):
        resp = await client.post("/runs", data={"params": json.dumps({"input": "x", "outdir": "/out"})})
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert "id" in data


@pytest.mark.asyncio
async def test_submit_run_creates_artifacts_and_completes(client):
    class FakeProcess:
        def __init__(self, log_path: Path, outdir: Path):
            self.pid = 4242
            self._log_path = log_path
            self._outdir = outdir

        async def wait(self):
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_path.write_text("nextflow log contents\n")
            self._outdir.mkdir(parents=True, exist_ok=True)
            (self._outdir / "result.txt").write_text("ok\n")
            return 0

    async def fake_create_subprocess_exec(*cmd, cwd=None, **kwargs):
        log_path = Path(cwd) / cmd[cmd.index("-log") + 1]
        outdir = Path(cwd) / cmd[-1]
        return FakeProcess(log_path, outdir)

    with patch("app.runner.asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec):
        resp = await client.post("/runs", data={"params": json.dumps({"input": "x", "outdir": "/out"})})

    assert resp.status_code == 202
    run_id = resp.json()["id"]

    from app.main import app

    run_dir = Path(app.state.config.RUN_DIR) / run_id
    assert (run_dir / "nextflow.log").read_text() == "nextflow log contents\n"
    assert (run_dir / "results" / "result.txt").read_text() == "ok\n"

    detail = await client.get(f"/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_get_run_not_found(client):
    resp = await client.get("/runs/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_runs_empty(client):
    resp = await client.get("/runs")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_runs_status_filter(client):
    with patch("app.routes.runs.launch_run", new_callable=AsyncMock):
        r1 = await client.post("/runs", data={"params": json.dumps({})})
        r2 = await client.post("/runs", data={"params": json.dumps({})})
    run_id_1 = r1.json()["id"]

    from app.main import app
    db = app.state.db
    await update_run(db, run_id_1, status=RunStatus.completed)

    resp = await client.get("/runs?status=completed")
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()]
    assert run_id_1 in ids


@pytest.mark.asyncio
async def test_get_logs_empty_when_no_file(client):
    with patch("app.routes.runs.launch_run", new_callable=AsyncMock):
        r = await client.post("/runs", data={"params": json.dumps({})})
    run_id = r.json()["id"]
    resp = await client.get(f"/runs/{run_id}/logs")
    assert resp.status_code == 200
    assert resp.text == ""


@pytest.mark.asyncio
async def test_get_logs_returns_log_contents(client):
    with patch("app.routes.runs.launch_run", new_callable=AsyncMock):
        r = await client.post("/runs", data={"params": json.dumps({})})
    run_id = r.json()["id"]

    from app.main import app

    log_path = Path(app.state.config.RUN_DIR) / run_id / "nextflow.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("hello from nextflow\n")

    resp = await client.get(f"/runs/{run_id}/logs")
    assert resp.status_code == 200
    assert resp.text == "hello from nextflow\n"


@pytest.mark.asyncio
async def test_cancel_non_running_run_returns_409(client):
    with patch("app.routes.runs.launch_run", new_callable=AsyncMock):
        r = await client.post("/runs", data={"params": json.dumps({})})
    run_id = r.json()["id"]
    resp = await client.delete(f"/runs/{run_id}")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_cancel_running_run_returns_204(client):
    with patch("app.routes.runs.launch_run", new_callable=AsyncMock):
        r = await client.post("/runs", data={"params": json.dumps({})})
    run_id = r.json()["id"]

    from app.main import app
    db = app.state.db
    await update_run(db, run_id, status=RunStatus.running, pid=99999)

    with patch("app.runner.os.kill"):
        resp = await client.delete(f"/runs/{run_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_submit_run_with_file_upload(client):
    with patch("app.routes.runs.launch_run", new_callable=AsyncMock):
        resp = await client.post(
            "/runs",
            data={"params": json.dumps({})},
            files=[("files", ("samplesheet.csv", b"sample,path\nA,/data/a.fastq", "text/csv"))],
        )
    assert resp.status_code == 202
    run_id = resp.json()["id"]

    from app.main import app
    input_file = Path(app.state.config.RUN_DIR) / run_id / "input" / "samplesheet.csv"
    assert input_file.read_bytes() == b"sample,path\nA,/data/a.fastq"
