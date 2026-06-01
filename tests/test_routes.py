import pytest
import pytest_asyncio
import aiosqlite
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from app.database import update_run
from app.models import RunStatus


@pytest_asyncio.fixture
async def client(tmp_path):
    """Provide a test client with temp DB and work dir."""
    import app.config as cfg
    cfg.DB_PATH = str(tmp_path / "test.db")
    cfg.RUN_DIR = str(tmp_path / "work")
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
        resp = await client.post("/runs", json={"params": {"input": "x", "outdir": "/out"}})
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert "id" in data


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
        r1 = await client.post("/runs", json={"params": {}})
        r2 = await client.post("/runs", json={"params": {}})
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
        r = await client.post("/runs", json={"params": {}})
    run_id = r.json()["id"]
    resp = await client.get(f"/runs/{run_id}/logs")
    assert resp.status_code == 200
    assert resp.text == ""


@pytest.mark.asyncio
async def test_cancel_non_running_run_returns_409(client):
    with patch("app.routes.runs.launch_run", new_callable=AsyncMock):
        r = await client.post("/runs", json={"params": {}})
    run_id = r.json()["id"]
    resp = await client.delete(f"/runs/{run_id}")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_cancel_running_run_returns_204(client):
    with patch("app.routes.runs.launch_run", new_callable=AsyncMock):
        r = await client.post("/runs", json={"params": {}})
    run_id = r.json()["id"]

    from app.main import app
    db = app.state.db
    await update_run(db, run_id, status=RunStatus.running, pid=99999)

    with patch("app.runner.os.kill"):
        resp = await client.delete(f"/runs/{run_id}")
    assert resp.status_code == 204
