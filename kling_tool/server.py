"""Unified FastAPI server — mounts all routers, adds /api/generate, /health, /outputs.

This is the single entry point for Docker. Run with:
    uvicorn kling_tool.server:app --host 0.0.0.0 --port 8686
"""

from __future__ import annotations

import logging
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config as cfg
from .accounts import AccountManager
from .api import router as api_router
from .dashboard import router as dashboard_router
from .database import Database
from .models import Task, TaskStatus
from .watcher import AccountWatcher
from .worker import Worker

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, accounts, worker, watcher. Shutdown: stop all."""
    cfg.ensure_dirs()

    db = Database()
    accounts = AccountManager(db)
    worker = Worker(db)
    watcher = AccountWatcher(accounts)

    app.state.db = db
    app.state.accounts = accounts
    app.state.worker = worker
    app.state.watcher = watcher

    worker.start()
    watcher.start()
    log.info("Server started — worker + watcher running")

    yield

    worker.stop()
    watcher.stop()
    log.info("Server stopped")


app = FastAPI(
    title="Kling Tool",
    description="Motion Control video generation — multi-account proxy with web UI credits",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Mount routers
app.include_router(api_router)       # /v1/... official API format
app.include_router(dashboard_router)  # /api/... dashboard + GET / HTML

# Serve output videos as static files
cfg.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(cfg.OUTPUTS_DIR)), name="outputs")


# ── ALL-IN-ONE endpoint ──────────────────────────────────────

@app.post("/api/generate")
async def generate(
    image: UploadFile = File(..., description="Character image (.jpg/.png)"),
    video: UploadFile = File(..., description="Motion reference video (.mp4/.mov)"),
    prompt: str = Form(""),
    mode: str = Form("pro"),
    model_name: str = Form("kling-v2-6"),
    orientation: str = Form("image"),
    keep_sound: str = Form("yes"),
):
    """Upload image + video and create a motion control task in one request.

    Returns task_id immediately. Poll GET /api/tasks/{task_id} for status.
    When done, download from result_video_url (e.g. /outputs/task_42.mp4).
    """
    db = app.state.db

    # Validate image
    img_ext = Path(image.filename).suffix.lower()
    if img_ext not in (".jpg", ".jpeg", ".png"):
        raise HTTPException(400, f"Invalid image type: {img_ext}. Use .jpg or .png")

    # Validate video
    vid_ext = Path(video.filename).suffix.lower()
    if vid_ext not in (".mp4", ".mov"):
        raise HTTPException(400, f"Invalid video type: {vid_ext}. Use .mp4 or .mov")

    # Save image
    img_name = f"{uuid.uuid4().hex[:8]}_{image.filename}"
    img_path = cfg.IMAGES_DIR / img_name
    with open(img_path, "wb") as f:
        shutil.copyfileobj(image.file, f)

    # Save video
    vid_name = f"{uuid.uuid4().hex[:8]}_{video.filename}"
    vid_path = cfg.VIDEOS_DIR / vid_name
    with open(vid_path, "wb") as f:
        shutil.copyfileobj(video.file, f)

    # Create task
    ext_id = f"gen-{uuid.uuid4().hex[:8]}"
    task = Task(
        external_task_id=ext_id,
        image_url=str(img_path),
        video_url=str(vid_path),
        prompt=prompt,
        model_name=model_name,
        mode=mode,
        character_orientation=orientation,
        keep_original_sound=keep_sound,
    )
    task_id = db.add_task(task)

    return {
        "code": 0,
        "message": "Task queued",
        "data": {
            "task_id": task_id,
            "external_task_id": ext_id,
            "status": "queued",
            "image": img_name,
            "video": vid_name,
        },
    }


# ── Health check ─────────────────────────────────────────────

@app.get("/health")
def health():
    """Docker healthcheck endpoint."""
    db = app.state.db
    accounts = app.state.accounts
    worker = app.state.worker

    stats = accounts.pool_stats()
    queued = len(db.get_tasks(status="queued"))

    return {
        "status": "ok",
        "worker_running": worker.is_running(),
        "active_accounts": stats["active_accounts"],
        "total_credits": stats["total_credits_remaining"],
        "queued_tasks": queued,
    }
