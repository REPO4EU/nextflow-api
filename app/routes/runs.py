from __future__ import annotations
import json
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response, FileResponse

from app.auth import get_current_user
from app.database import delete_run, get_run, insert_run, list_runs
from app.models import RunListItem, RunResponse, RunStatus, SubmitResponse
from app.runner import cancel_run, launch_run

router = APIRouter(prefix="/runs", tags=["runs"])


def _get_db(request: Request) -> aiosqlite.Connection:
    return request.app.state.db


async def _get_owned_run(db: aiosqlite.Connection, run_id: str, user_id: str) -> dict[str, object]:
    row = await get_run(db, run_id, user_id=user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return row


@router.post("", response_model=SubmitResponse, status_code=202)
async def submit_run(
    background_tasks: BackgroundTasks,
    request: Request,
    params: str = Form(default="{}"),
    workflow: str = Form(default=""),
    profile: str = Form(default="docker"),
    files: list[UploadFile] = File(default=[]),
    user_id: str = Depends(get_current_user),
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
        if isinstance(value, bool):
            if value:
                cmd.append(f"--{key}")
        elif value is None:
            continue
        else:
            cmd += [f"--{key}", str(value)]
    cmd += ["--outdir", "results"]

    created_at = datetime.now(timezone.utc).isoformat()
    await insert_run(
        db,
        run_id=run_id,
        params=params_dict,
        command=" ".join(cmd),
        run_dir=str(run_dir),
        created_at=created_at,
        user_id=user_id,
        workflow_name=workflow or None,
    )
    background_tasks.add_task(launch_run, db=db, run_id=run_id, cmd=cmd, cwd=str(run_dir))
    return SubmitResponse(id=run_id, status=RunStatus.queued)


@router.get("", response_model=list[RunListItem])
async def list_all_runs(
    request: Request,
    user_id: str = Depends(get_current_user),
    status: Optional[RunStatus] = None,
) -> list[RunListItem]:
    db = _get_db(request)
    rows = await list_runs(db, status=status, user_id=user_id)
    return [RunListItem(**r) for r in rows]


@router.get("/{run_id}", response_model=RunResponse)
async def get_run_detail(
    run_id: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> RunResponse:
    db = _get_db(request)
    row = await _get_owned_run(db, run_id, user_id)
    return RunResponse(**row)


@router.get("/{run_id}/logs", response_class=PlainTextResponse)
async def get_run_logs(
    run_id: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> str:
    db = _get_db(request)
    await _get_owned_run(db, run_id, user_id)
    cfg = request.app.state.config
    log_path = Path(cfg.RUN_DIR) / run_id / "nextflow.log"
    if not log_path.exists():
        return ""
    return log_path.read_text()


@router.post("/{run_id}/cancel", status_code=204, response_class=Response)
async def cancel_run_endpoint(
    run_id: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> Response:
    db = _get_db(request)
    row = await _get_owned_run(db, run_id, user_id)
    if row["status"] != RunStatus.running:
        raise HTTPException(status_code=409, detail=f"Run is not running (status: {row['status']})")
    await cancel_run(db, run_id)
    return Response(status_code=204)


@router.delete("/{run_id}", status_code=204, response_class=Response)
async def delete_run_endpoint(
    run_id: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> Response:
    db = _get_db(request)
    row = await _get_owned_run(db, run_id, user_id)
    if row["status"] == RunStatus.running:
        raise HTTPException(status_code=409, detail="Cannot delete a running run")

    cfg = request.app.state.config
    run_dir = Path(cfg.RUN_DIR) / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    zip_path = run_dir.parent / f"{run_id}.zip"
    if zip_path.exists():
        zip_path.unlink()

    await delete_run(db, run_id)
    return Response(status_code=204)
def _zip_run_dir(run_dir: Path, zip_path: Path) -> Path:
    # Create a zip archive of the run directory at zip_path (including the run_dir contents)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(run_dir.rglob('*')):
            if path.is_file():
                archive.write(path, arcname=str(path.relative_to(run_dir)))
    return zip_path


@router.get("/{run_id}/download")
async def download_run_zip(
    run_id: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> FileResponse:
    db = _get_db(request)
    await _get_owned_run(db, run_id, user_id)
    cfg = request.app.state.config
    run_dir = Path(cfg.RUN_DIR) / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")

    zip_path = run_dir.parent / f"{run_id}.zip"
    # (Re)create zip archive outside the run directory to avoid nesting
    try:
        _zip_run_dir(run_dir, zip_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create zip: {e}")

    return FileResponse(path=str(zip_path), filename=f"{run_id}.zip", media_type="application/zip")


def _validate_input_filename(filename: str) -> None:
    if not filename or filename in {".", ".."}:
        raise HTTPException(status_code=422, detail="Invalid filename")
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=422, detail="Invalid filename")
    if Path(filename).name != filename or Path(filename).is_absolute():
        raise HTTPException(status_code=422, detail="Invalid filename")


@router.get("/{run_id}/download/input/{filename}")
async def download_run_input_file(
    run_id: str,
    filename: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> FileResponse:
    db = _get_db(request)
    await _get_owned_run(db, run_id, user_id)
    _validate_input_filename(filename)

    cfg = request.app.state.config
    input_path = Path(cfg.RUN_DIR) / run_id / "input" / filename
    if not input_path.exists() or not input_path.is_file():
        raise HTTPException(status_code=404, detail="Input file not found")

    return FileResponse(path=str(input_path), filename=filename, media_type="application/octet-stream")


# (no singular `/run` alias)
