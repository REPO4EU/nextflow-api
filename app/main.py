from __future__ import annotations
import shutil
from contextlib import asynccontextmanager

import aiosqlite
from fastapi import FastAPI

from app import config as cfg
from app.database import init_db
from app.routes.runs import router as runs_router
from app.routes.health import router as health_router
from app.runner import reattach_running_runs
from app.consul import register_service, deregister_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not shutil.which(cfg.NEXTFLOW_BIN):
        raise RuntimeError(f"Nextflow binary not found: {cfg.NEXTFLOW_BIN}")
    db = await aiosqlite.connect(cfg.DB_PATH)
    await init_db(db)
    app.state.db = db
    app.state.config = cfg
    await reattach_running_runs(db)
    
    # Register with Consul
    register_service()
    
    yield
    
    # Deregister from Consul
    deregister_service()
    
    await db.close()


app = FastAPI(title="Nextflow API", lifespan=lifespan)
app.include_router(health_router)
app.include_router(runs_router)
