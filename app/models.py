from __future__ import annotations
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"



class SubmitResponse(BaseModel):
    id: str
    status: RunStatus


class RunResponse(BaseModel):
    id: str
    user_id: Optional[str]
    status: RunStatus
    params: dict[str, Any]
    command: Optional[str]
    run_dir: Optional[str]
    created_at: str
    started_at: Optional[str]
    finished_at: Optional[str]
    exit_code: Optional[int]


class RunListItem(BaseModel):
    id: str
    user_id: str
    status: RunStatus
    created_at: str
    started_at: Optional[str]
    finished_at: Optional[str]
