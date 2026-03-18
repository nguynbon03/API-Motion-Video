"""REST API Router — drop-in replacement for official Kling Motion Control API.

Mounted by server.py. Accesses shared state via request.app.state.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .models import Task, TaskStatus

log = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response models ────────────────────────────────

class MotionControlRequest(BaseModel):
    model_name: str = Field(default="kling-v2-6")
    image_url: str = Field(...)
    video_url: str = Field(...)
    prompt: str = Field(default="")
    mode: str = Field(default="pro")
    character_orientation: str = Field(default="image")
    keep_original_sound: str = Field(default="yes")
    callback_url: str = Field(default="")
    external_task_id: str = Field(default="")


class TaskResponse(BaseModel):
    code: int = 0
    message: str = "success"
    request_id: str = ""
    data: dict = {}


class AccountAddRequest(BaseModel):
    name: str
    email: str
    password: str
    proxy: str = ""
    credits: float = 66.0


class BulkAccountRequest(BaseModel):
    accounts: list[str] = Field(...)
    default_credits: float = 66.0


# ── Helpers ──────────────────────────────────────────────────

def _db(request: Request):
    return request.app.state.db

def _accounts(request: Request):
    return request.app.state.accounts

def _worker(request: Request):
    return request.app.state.worker


# ── Motion Control endpoints (mirrors official API) ──────────

@router.post("/v1/videos/motion-control", response_model=TaskResponse)
def create_motion_task(req: MotionControlRequest, request: Request):
    db = _db(request)
    request_id = str(uuid.uuid4())
    ext_id = req.external_task_id or f"api-{uuid.uuid4().hex[:12]}"

    task = Task(
        external_task_id=ext_id,
        image_url=req.image_url,
        video_url=req.video_url,
        prompt=req.prompt,
        model_name=req.model_name,
        mode=req.mode,
        character_orientation=req.character_orientation,
        keep_original_sound=req.keep_original_sound,
        status=TaskStatus.QUEUED.value,
    )

    task_id = db.add_task(task)
    return TaskResponse(
        code=0, message="Task queued", request_id=request_id,
        data={"task_id": str(task_id), "external_task_id": ext_id, "task_status": "queued"},
    )


@router.get("/v1/videos/motion-control/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, request: Request):
    task = _db(request).get_task(task_id)
    if not task:
        return TaskResponse(code=404, message="Task not found", data={})

    data = {
        "task_id": str(task["id"]),
        "external_task_id": task["external_task_id"],
        "task_status": task["status"],
        "task_info": {"account": task["account_name"], "model_name": task["model_name"], "mode": task["mode"]},
    }
    if task["status"] == TaskStatus.SUCCEED.value:
        data["task_result"] = {"videos": [{"url": task["result_video_url"], "duration": task["duration"]}]}
    if task["status"] == TaskStatus.FAILED.value:
        data["error"] = task["error_message"]

    return TaskResponse(code=0, message="success", data=data)


@router.get("/v1/videos/motion-control", response_model=TaskResponse)
def list_tasks(request: Request, pageNum: int = Query(1, ge=1), pageSize: int = Query(30, ge=1, le=100), status: Optional[str] = None):
    tasks = _db(request).get_tasks(status=status, page=pageNum, size=pageSize)
    return TaskResponse(code=0, message="success", data={
        "tasks": [
            {"task_id": str(t["id"]), "external_task_id": t["external_task_id"],
             "task_status": t["status"], "account": t["account_name"],
             "created_at": t["created_at"], "completed_at": t["completed_at"],
             "result_video_url": t["result_video_url"]}
            for t in tasks
        ],
        "page": pageNum, "page_size": pageSize,
    })


# ── Pool management endpoints ────────────────────────────────

@router.get("/v1/pool/status")
def pool_status(request: Request):
    db, accounts, worker = _db(request), _accounts(request), _worker(request)
    stats = accounts.pool_stats()
    stats["queued_tasks"] = len(db.get_tasks(status="queued"))
    stats["processing_tasks"] = len(db.get_tasks(status="processing"))
    stats["worker_running"] = worker.is_running() if worker else False
    return {"code": 0, "data": stats}


@router.post("/v1/pool/accounts")
def add_account(req: AccountAddRequest, request: Request):
    try:
        row_id = _accounts(request).add(req.name, req.email, req.password, req.proxy, req.credits)
        return {"code": 0, "message": "Account added", "data": {"id": row_id, "name": req.name}}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/v1/pool/accounts/bulk")
def add_accounts_bulk(req: BulkAccountRequest, request: Request):
    count = _accounts(request).add_bulk(req.accounts, req.default_credits)
    return {"code": 0, "message": f"{count} accounts added", "data": {"count": count}}


@router.get("/v1/pool/accounts")
def list_accounts(request: Request):
    return {"code": 0, "data": _accounts(request).pool_stats()}


@router.delete("/v1/pool/accounts/{name}")
def remove_account(name: str, request: Request):
    if _accounts(request).remove(name):
        return {"code": 0, "message": f"Account '{name}' removed"}
    raise HTTPException(404)


@router.put("/v1/pool/accounts/{name}/credits")
def set_credits(name: str, request: Request, credits: float = Query(...)):
    if _accounts(request).set_credits(name, credits):
        return {"code": 0, "message": f"Credits set to {credits}"}
    raise HTTPException(404)
