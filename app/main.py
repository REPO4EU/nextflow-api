from __future__ import annotations
import shutil
import logging
from contextlib import asynccontextmanager

import aiosqlite
from fastapi import FastAPI

from app import config as cfg
from app.database import init_db
from app.routes.runs import router as runs_router
from app.routes.health import router as health_router
from app.runner import QueueWorker, reattach_running_runs
from app.consul import register_service, deregister_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not shutil.which(cfg.NEXTFLOW_BIN):
        logger.warning("Nextflow binary not found at startup: %s; queued runs will be retried", cfg.NEXTFLOW_BIN)
    db = await aiosqlite.connect(cfg.DB_PATH)
    await init_db(db)
    app.state.db = db
    app.state.config = cfg
    if cfg.MAX_CONCURRENT_RUNS < 1:
        raise RuntimeError("MAX_CONCURRENT_RUNS must be at least 1")
    recovered_tasks = await reattach_running_runs(db)
    queue_worker = QueueWorker(db, cfg.MAX_CONCURRENT_RUNS, recovered_tasks)
    app.state.queue_worker = queue_worker
    queue_worker.start()
    
    # Register with Consul
    register_service()
    
    yield
    
    # Deregister from Consul
    deregister_service()
    await queue_worker.stop()
    await db.close()


app = FastAPI(title="Nextflow API", lifespan=lifespan)
app.include_router(health_router)
app.include_router(runs_router)
