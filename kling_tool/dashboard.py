"""Web Dashboard Router — Upload files, manage accounts, create & monitor tasks.

Mounted by server.py. Accesses shared state via request.app.state.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse

from . import config as cfg
from .models import Task, TaskStatus

log = logging.getLogger(__name__)

router = APIRouter()


def _db(r: Request):
    return r.app.state.db

def _mgr(r: Request):
    return r.app.state.accounts

def _worker(r: Request):
    return r.app.state.worker


# ── Dashboard HTML ───────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def dashboard():
    return DASHBOARD_HTML


# ── File Upload ──────────────────────────────────────────────

@router.post("/api/upload/image")
async def upload_image(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png"):
        raise HTTPException(400, f"Invalid image type: {ext}")
    name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    path = cfg.IMAGES_DIR / name
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"name": name, "path": str(path), "size": path.stat().st_size}


@router.post("/api/upload/video")
async def upload_video(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in (".mp4", ".mov"):
        raise HTTPException(400, f"Invalid video type: {ext}")
    name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    path = cfg.VIDEOS_DIR / name
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"name": name, "path": str(path), "size": path.stat().st_size}


@router.post("/api/upload/accounts")
async def upload_accounts(request: Request, file: UploadFile = File(...), credits: float = Form(66.0)):
    content = (await file.read()).decode("utf-8")
    save_path = cfg.ACCOUNTS_DIR / file.filename
    save_path.write_text(content, encoding="utf-8")
    lines = content.splitlines()
    count = _mgr(request).add_bulk(lines, default_credits=credits)
    return {"filename": file.filename, "total_lines": len(lines), "imported": count}


# ── File Lists ───────────────────────────────────────────────

@router.get("/api/files/images")
def list_images():
    files = sorted(cfg.IMAGES_DIR.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
    return [{"name": f.name, "path": str(f), "size": f.stat().st_size} for f in files if f.is_file()]


@router.get("/api/files/videos")
def list_videos():
    files = sorted(cfg.VIDEOS_DIR.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
    return [{"name": f.name, "path": str(f), "size": f.stat().st_size} for f in files if f.is_file()]


# ── Tasks ────────────────────────────────────────────────────

@router.post("/api/tasks")
def create_task(
    request: Request,
    image_path: str = Form(...),
    video_path: str = Form(...),
    prompt: str = Form(""),
    mode: str = Form("pro"),
    model_name: str = Form("kling-v2-6"),
    orientation: str = Form("image"),
    keep_sound: str = Form("yes"),
):
    ext_id = f"web-{uuid.uuid4().hex[:8]}"
    task = Task(
        external_task_id=ext_id, image_url=image_path, video_url=video_path,
        prompt=prompt, model_name=model_name, mode=mode,
        character_orientation=orientation, keep_original_sound=keep_sound,
    )
    tid = _db(request).add_task(task)
    return {"task_id": tid, "external_id": ext_id, "status": "queued"}


@router.get("/api/tasks")
def list_tasks(request: Request, page: int = 1, size: int = 50, status: Optional[str] = None):
    return _db(request).get_tasks(status=status, page=page, size=size)


@router.get("/api/tasks/{task_id}")
def get_task(task_id: int, request: Request):
    t = _db(request).get_task(task_id)
    if not t:
        raise HTTPException(404, "Task not found")
    return t


# ── Accounts ─────────────────────────────────────────────────

@router.get("/api/accounts")
def list_accounts(request: Request):
    return _mgr(request).pool_stats()


@router.delete("/api/accounts/{name}")
def remove_account(name: str, request: Request):
    if _mgr(request).remove(name):
        return {"ok": True}
    raise HTTPException(404)


# ── Status ───────────────────────────────────────────────────

@router.get("/api/status")
def pool_status(request: Request):
    db, mgr, worker = _db(request), _mgr(request), _worker(request)
    stats = mgr.pool_stats()
    queued = len(db.get_tasks(status="queued"))
    processing = len(db.get_tasks(status="processing"))
    succeed = len(db.get_tasks(status="succeed"))
    failed = len(db.get_tasks(status="failed"))
    return {
        **stats,
        "tasks": {"queued": queued, "processing": processing, "succeed": succeed, "failed": failed},
        "worker_running": worker.is_running() if worker else False,
    }


# ── HTML ─────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kling Tool Dashboard</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0a0a0a; color: #e0e0e0; }
.header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 20px 30px; border-bottom: 1px solid #2a2a4a; display: flex; align-items: center; justify-content: space-between; }
.header h1 { font-size: 22px; color: #4ade80; }
.header .status-bar { display: flex; gap: 20px; font-size: 13px; }
.header .stat { background: #1e1e3e; padding: 6px 14px; border-radius: 6px; }
.header .stat b { color: #4ade80; }
.main { display: grid; grid-template-columns: 340px 1fr; height: calc(100vh - 70px); }
.left-panel { background: #111; border-right: 1px solid #222; overflow-y: auto; padding: 16px; }
.section { margin-bottom: 20px; }
.section h3 { font-size: 13px; text-transform: uppercase; letter-spacing: 1px; color: #888; margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid #222; }
.upload-zone { border: 2px dashed #333; border-radius: 10px; padding: 20px; text-align: center; cursor: pointer; transition: all 0.2s; margin-bottom: 10px; }
.upload-zone:hover { border-color: #4ade80; background: #0d1f0d; }
.upload-zone.dragover { border-color: #4ade80; background: #1a3a1a; }
.upload-zone input { display: none; }
.upload-zone .icon { font-size: 28px; margin-bottom: 6px; }
.upload-zone .label { font-size: 13px; color: #aaa; }
.upload-zone .label b { color: #4ade80; }
.file-list { max-height: 120px; overflow-y: auto; }
.file-item { display: flex; justify-content: space-between; align-items: center; padding: 5px 8px; background: #1a1a1a; border-radius: 4px; margin: 3px 0; font-size: 12px; cursor: pointer; transition: background 0.15s; }
.file-item:hover { background: #222; }
.file-item.selected { background: #1a3a1a; border: 1px solid #4ade80; }
.file-item .size { color: #666; font-size: 11px; }
.form-group { margin-bottom: 12px; }
.form-group label { display: block; font-size: 12px; color: #888; margin-bottom: 4px; }
.form-group input, .form-group select, .form-group textarea { width: 100%; background: #1a1a1a; border: 1px solid #333; color: #e0e0e0; padding: 8px 10px; border-radius: 6px; font-size: 13px; }
.form-group textarea { resize: vertical; min-height: 50px; }
.btn { display: inline-flex; align-items: center; justify-content: center; padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; transition: all 0.2s; width: 100%; }
.btn-primary { background: #4ade80; color: #000; }
.btn-primary:hover { background: #22c55e; transform: translateY(-1px); }
.btn-primary:disabled { background: #333; color: #666; cursor: not-allowed; transform: none; }
.btn-secondary { background: #2a2a4a; color: #aaa; margin-top: 6px; }
.btn-secondary:hover { background: #3a3a5a; }
.btn-sm { padding: 5px 12px; font-size: 12px; width: auto; }
.right-panel { overflow-y: auto; padding: 16px; }
.accounts-bar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.account-chip { display: flex; align-items: center; gap: 6px; background: #1a1a2e; padding: 6px 12px; border-radius: 20px; font-size: 12px; }
.account-chip .dot { width: 8px; height: 8px; border-radius: 50%; }
.account-chip .dot.active { background: #4ade80; }
.account-chip .dot.disabled { background: #ef4444; }
.task-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.task-table th { text-align: left; padding: 10px; background: #1a1a2e; color: #888; font-weight: 500; border-bottom: 1px solid #333; position: sticky; top: 0; }
.task-table td { padding: 8px 10px; border-bottom: 1px solid #1a1a1a; }
.task-table tr:hover td { background: #111; }
.badge { padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.badge-queued { background: #1e3a5f; color: #60a5fa; }
.badge-submitted { background: #3b1f5e; color: #c084fc; }
.badge-processing { background: #3b3a1f; color: #facc15; }
.badge-succeed { background: #1a3a1a; color: #4ade80; }
.badge-failed { background: #3a1a1a; color: #ef4444; }
.empty-state { text-align: center; padding: 40px; color: #555; }
.toast { position: fixed; bottom: 20px; right: 20px; background: #1a3a1a; color: #4ade80; padding: 12px 20px; border-radius: 8px; font-size: 13px; border: 1px solid #2a4a2a; z-index: 999; display: none; animation: slideIn 0.3s ease; }
@keyframes slideIn { from { transform: translateY(20px); opacity: 0; } }
</style>
</head>
<body>
<div class="header">
    <h1>&#9889; Kling Tool Dashboard</h1>
    <div class="status-bar">
        <div class="stat">Accounts: <b id="stat-accounts">0</b></div>
        <div class="stat">Credits: <b id="stat-credits">0</b></div>
        <div class="stat">Queued: <b id="stat-queued">0</b></div>
        <div class="stat">Processing: <b id="stat-processing">0</b></div>
        <div class="stat">Done: <b id="stat-succeed">0</b></div>
        <div class="stat">Worker: <b id="stat-worker">-</b></div>
    </div>
</div>
<div class="main">
    <div class="left-panel">
        <div class="section">
            <h3>&#128100; Accounts</h3>
            <div class="upload-zone" onclick="document.getElementById('accounts-input').click()" ondragover="event.preventDefault();this.classList.add('dragover')" ondragleave="this.classList.remove('dragover')" ondrop="handleDrop(event,'accounts-input')">
                <div class="icon">&#128196;</div>
                <div class="label">Drop <b>accounts.txt</b> here<br>or click to upload</div>
                <input type="file" id="accounts-input" accept=".txt,.csv" onchange="uploadAccounts(this)">
            </div>
            <div class="form-group"><label>Default credits per account</label><input type="number" id="default-credits" value="66" min="0" step="1"></div>
            <div id="accounts-list" class="accounts-bar"></div>
        </div>
        <div class="section">
            <h3>&#128247; Character Images</h3>
            <div class="upload-zone" onclick="document.getElementById('image-input').click()" ondragover="event.preventDefault();this.classList.add('dragover')" ondragleave="this.classList.remove('dragover')" ondrop="handleDrop(event,'image-input')">
                <div class="icon">&#128444;</div>
                <div class="label">Drop <b>.jpg / .png</b> here<br>or click to upload</div>
                <input type="file" id="image-input" accept=".jpg,.jpeg,.png" multiple onchange="uploadImages(this)">
            </div>
            <div id="images-list" class="file-list"></div>
        </div>
        <div class="section">
            <h3>&#127909; Motion Videos</h3>
            <div class="upload-zone" onclick="document.getElementById('video-input').click()" ondragover="event.preventDefault();this.classList.add('dragover')" ondragleave="this.classList.remove('dragover')" ondrop="handleDrop(event,'video-input')">
                <div class="icon">&#127916;</div>
                <div class="label">Drop <b>.mp4 / .mov</b> here<br>or click to upload</div>
                <input type="file" id="video-input" accept=".mp4,.mov" multiple onchange="uploadVideos(this)">
            </div>
            <div id="videos-list" class="file-list"></div>
        </div>
        <div class="section">
            <h3>&#128640; Create Motion Task</h3>
            <div class="form-group"><label>Selected Image</label><input type="text" id="sel-image" readonly placeholder="Click an image above"></div>
            <div class="form-group"><label>Selected Video</label><input type="text" id="sel-video" readonly placeholder="Click a video above"></div>
            <div class="form-group"><label>Prompt (optional)</label><textarea id="task-prompt" placeholder="Describe the character..."></textarea></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                <div class="form-group"><label>Mode</label><select id="task-mode"><option value="pro">Pro</option><option value="std">Standard</option></select></div>
                <div class="form-group"><label>Orientation</label><select id="task-orientation"><option value="image">Match Image</option><option value="video">Match Video</option></select></div>
            </div>
            <div class="form-group"><label>Keep Sound</label><select id="task-sound"><option value="yes">Yes</option><option value="no">No</option></select></div>
            <button class="btn btn-primary" id="btn-generate" onclick="createTask()" disabled>&#9889; Generate Motion Video</button>
        </div>
    </div>
    <div class="right-panel">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <h2 style="font-size:16px;">Task History</h2>
            <button class="btn btn-sm btn-secondary" onclick="refreshAll()">&#128260; Refresh</button>
        </div>
        <table class="task-table">
            <thead><tr><th>ID</th><th>Status</th><th>Account</th><th>Mode</th><th>Image</th><th>Video</th><th>Created</th><th>Result</th></tr></thead>
            <tbody id="tasks-body"><tr><td colspan="8" class="empty-state">No tasks yet. Upload files and create a task.</td></tr></tbody>
        </table>
    </div>
</div>
<div class="toast" id="toast"></div>
<script>
let selectedImage='',selectedVideo='';
function handleDrop(e,id){e.preventDefault();e.currentTarget.classList.remove('dragover');const i=document.getElementById(id);i.files=e.dataTransfer.files;i.dispatchEvent(new Event('change'));}
async function uploadAccounts(i){const f=i.files[0];if(!f)return;const d=new FormData();d.append('file',f);d.append('credits',document.getElementById('default-credits').value);const r=await fetch('/api/upload/accounts',{method:'POST',body:d});const j=await r.json();toast('Imported '+j.imported+' accounts');loadAccounts();loadStatus();}
async function uploadImages(i){for(const f of i.files){const d=new FormData();d.append('file',f);await fetch('/api/upload/image',{method:'POST',body:d});}toast('Uploaded '+i.files.length+' image(s)');loadImages();}
async function uploadVideos(i){for(const f of i.files){const d=new FormData();d.append('file',f);await fetch('/api/upload/video',{method:'POST',body:d});}toast('Uploaded '+i.files.length+' video(s)');loadVideos();}
async function loadImages(){const r=await fetch('/api/files/images');const fs=await r.json();document.getElementById('images-list').innerHTML=fs.map(f=>'<div class="file-item '+(selectedImage===f.path?'selected':'')+'" onclick="selectImage(\''+f.path.replace(/\\\\/g,'\\\\\\\\')+'\',\''+f.name+'\')"><span>'+(f.name.length>28?f.name.slice(0,28)+'...':f.name)+'</span><span class="size">'+(f.size/1024).toFixed(0)+'KB</span></div>').join('');}
async function loadVideos(){const r=await fetch('/api/files/videos');const fs=await r.json();document.getElementById('videos-list').innerHTML=fs.map(f=>'<div class="file-item '+(selectedVideo===f.path?'selected':'')+'" onclick="selectVideo(\''+f.path.replace(/\\\\/g,'\\\\\\\\')+'\',\''+f.name+'\')"><span>'+(f.name.length>28?f.name.slice(0,28)+'...':f.name)+'</span><span class="size">'+(f.size/1024/1024).toFixed(1)+'MB</span></div>').join('');}
function selectImage(p,n){selectedImage=p;document.getElementById('sel-image').value=n;loadImages();checkReady();}
function selectVideo(p,n){selectedVideo=p;document.getElementById('sel-video').value=n;loadVideos();checkReady();}
function checkReady(){document.getElementById('btn-generate').disabled=!(selectedImage&&selectedVideo);}
async function createTask(){const b=document.getElementById('btn-generate');b.disabled=true;b.textContent='Creating...';const d=new FormData();d.append('image_path',selectedImage);d.append('video_path',selectedVideo);d.append('prompt',document.getElementById('task-prompt').value);d.append('mode',document.getElementById('task-mode').value);d.append('orientation',document.getElementById('task-orientation').value);d.append('keep_sound',document.getElementById('task-sound').value);const r=await fetch('/api/tasks',{method:'POST',body:d});const j=await r.json();toast('Task #'+j.task_id+' queued!');b.textContent='\\u26A1 Generate Motion Video';b.disabled=false;loadTasks();loadStatus();}
async function loadTasks(){const r=await fetch('/api/tasks?size=50');const ts=await r.json();const el=document.getElementById('tasks-body');if(!ts.length){el.innerHTML='<tr><td colspan="8" class="empty-state">No tasks yet.</td></tr>';return;}el.innerHTML=ts.map(t=>'<tr><td>#'+t.id+'</td><td><span class="badge badge-'+t.status+'">'+t.status.toUpperCase()+'</span></td><td>'+(t.account_name||'\\u2014')+'</td><td>'+t.mode+'</td><td title="'+t.image_url+'">'+(t.image_url||'').split(/[\\\\/]/).pop().slice(0,20)+'</td><td title="'+t.video_url+'">'+(t.video_url||'').split(/[\\\\/]/).pop().slice(0,20)+'</td><td>'+(t.created_at||'').slice(0,19)+'</td><td>'+(t.result_video_url?'<a href="'+t.result_video_url+'" target="_blank" style="color:#4ade80">Download</a>':'\\u2014')+'</td></tr>').join('');}
async function loadAccounts(){const r=await fetch('/api/accounts');const d=await r.json();document.getElementById('accounts-list').innerHTML=(d.accounts||[]).map(a=>'<div class="account-chip"><span class="dot '+(a.status==='active'?'active':'disabled')+'"></span>'+a.name+' ('+a.credits_remaining.toFixed(0)+')</div>').join('');}
async function loadStatus(){const r=await fetch('/api/status');const s=await r.json();document.getElementById('stat-accounts').textContent=s.active_accounts+'/'+s.total_accounts;document.getElementById('stat-credits').textContent=s.total_credits_remaining.toFixed(0);document.getElementById('stat-queued').textContent=s.tasks.queued;document.getElementById('stat-processing').textContent=s.tasks.processing;document.getElementById('stat-succeed').textContent=s.tasks.succeed;document.getElementById('stat-worker').textContent=s.worker_running?'ON':'OFF';document.getElementById('stat-worker').style.color=s.worker_running?'#4ade80':'#ef4444';}
function toast(m){const e=document.getElementById('toast');e.textContent=m;e.style.display='block';setTimeout(()=>{e.style.display='none';},3000);}
function refreshAll(){loadStatus();loadAccounts();loadImages();loadVideos();loadTasks();}
refreshAll();setInterval(loadStatus,5000);setInterval(loadTasks,10000);
</script>
</body>
</html>
"""
