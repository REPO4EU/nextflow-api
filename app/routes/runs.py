from __future__ import annotations
import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response

from app.database import get_run, insert_run, list_runs
from app.models import RunListItem, RunResponse, RunStatus, SubmitRequest, SubmitResponse
from app.runner import cancel_run, launch_run

router = APIRouter(prefix="/runs", tags=["runs"])


def _get_db(request: Request) -> aiosqlite.Connection:
    return request.app.state.db


@router.post("", response_model=SubmitResponse, status_code=202)
async def submit_run(
    body: SubmitRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> SubmitResponse:
    db = _get_db(request)
    cfg = request.app.state.config
    run_id = str(uuid.uuid4())
    run_dir = Path(cfg.RUN_DIR) / run_id
    run_work_dir = run_dir / "work"
    run_work_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "nextflow.log"
    outdir = run_dir / "results"

    cmd = [cfg.NEXTFLOW_BIN, "-log", str(log_path), "run", cfg.PIPELINE_PATH, "-c", "nextflow.config", "-profile", body.profile, "-work-dir", str(run_work_dir)]
    for key, value in body.params.items():
        cmd += [f"--{key}", str(value)]
    cmd += ["--outdir", str(outdir)]

    created_at = datetime.now(timezone.utc).isoformat()
    await insert_run(db, run_id=run_id, params=body.params, command=" ".join(cmd), run_dir=str(run_dir), created_at=created_at)
    background_tasks.add_task(launch_run, db=db, run_id=run_id, cmd=cmd)
    return SubmitResponse(id=run_id, status=RunStatus.queued)


@router.get("", response_model=list[RunListItem])
async def list_all_runs(
    request: Request,
    status: Optional[RunStatus] = None,
) -> list[RunListItem]:
    db = _get_db(request)
    rows = await list_runs(db, status=status)
    return [RunListItem(**r) for r in rows]


@router.get("/{run_id}", response_model=RunResponse)
async def get_run_detail(run_id: str, request: Request) -> RunResponse:
    db = _get_db(request)
    row = await get_run(db, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunResponse(**row)


@router.get("/{run_id}/logs", response_class=PlainTextResponse)
async def get_run_logs(run_id: str, request: Request) -> str:
    cfg = request.app.state.config
    log_path = Path(cfg.RUN_DIR) / run_id / "nextflow.log"
    if not log_path.exists():
        return ""
    return log_path.read_text()


@router.delete("/{run_id}", status_code=204, response_class=Response)
async def cancel_run_endpoint(run_id: str, request: Request) -> Response:
    db = _get_db(request)
    row = await get_run(db, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if row["status"] != RunStatus.running:
        raise HTTPException(status_code=409, detail=f"Run is not running (status: {row['status']})")
    await cancel_run(db, run_id)
    return Response(status_code=204)
