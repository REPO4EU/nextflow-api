from __future__ import annotations
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response

from app.database import get_run, insert_run, list_runs
from app.models import RunListItem, RunResponse, RunStatus, SubmitResponse
from app.runner import cancel_run, launch_run

router = APIRouter(prefix="/runs", tags=["runs"])


def _get_db(request: Request) -> aiosqlite.Connection:
    return request.app.state.db


@router.post("", response_model=SubmitResponse, status_code=202)
async def submit_run(
    background_tasks: BackgroundTasks,
    request: Request,
    params: str = Form(default="{}"),
    profile: str = Form(default="docker"),
    files: list[UploadFile] = File(default=[]),
) -> SubmitResponse:
    try:
        params_dict = json.loads(params)
    except ValueError:
        raise HTTPException(status_code=422, detail="params must be valid JSON")

    db = _get_db(request)
    cfg = request.app.state.config
    run_id = str(uuid.uuid4())
    run_dir = Path(cfg.RUN_DIR) / run_id
    (run_dir / "work").mkdir(parents=True, exist_ok=True)

    if files:
        input_dir = run_dir / "input"
        input_dir.mkdir(exist_ok=True)
        for upload in files:
            filename = Path(upload.filename).name
            if not filename:
                raise HTTPException(status_code=422, detail="Invalid filename")
            with (input_dir / filename).open("wb") as f:
                shutil.copyfileobj(upload.file, f)

    cmd = [cfg.NEXTFLOW_BIN, "-log", "nextflow.log", "run", cfg.PIPELINE_PATH, "-c", "/app/nextflow.config", "-profile", profile, "-work-dir", "work"]
    for key, value in params_dict.items():
        cmd += [f"--{key}", str(value)]
    cmd += ["--outdir", "results"]

    created_at = datetime.now(timezone.utc).isoformat()
    await insert_run(db, run_id=run_id, params=params_dict, command=" ".join(cmd), run_dir=str(run_dir), created_at=created_at)
    background_tasks.add_task(launch_run, db=db, run_id=run_id, cmd=cmd, cwd=str(run_dir))
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
