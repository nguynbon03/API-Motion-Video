"""Data models for accounts, tasks, and proxies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AccountStatus(str, Enum):
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    DISABLED = "disabled"
    BANNED = "banned"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    SUCCEED = "succeed"
    FAILED = "failed"


@dataclass
class Account:
    id: Optional[int] = None
    name: str = ""
    email: str = ""
    password: str = ""
    proxy: str = ""                          # socks5://ip:port or http://ip:port
    cookies_file: str = ""                   # path to saved session
    credits_remaining: float = 0.0
    credits_used: float = 0.0
    status: str = AccountStatus.ACTIVE.value
    last_used_at: str = ""
    created_at: str = field(default_factory=_now)
    note: str = ""


@dataclass
class Task:
    id: Optional[int] = None
    external_task_id: str = ""
    account_name: str = ""
    image_url: str = ""                      # original input
    video_url: str = ""                      # original input
    prompt: str = ""
    model_name: str = "kling-v2-6"
    mode: str = "pro"
    character_orientation: str = "image"
    keep_original_sound: str = "yes"
    status: str = TaskStatus.QUEUED.value
    result_video_url: str = ""
    result_watermark_url: str = ""
    duration: float = 0.0
    error_message: str = ""
    kling_task_id: str = ""                  # task ID from Kling web
    created_at: str = field(default_factory=_now)
    completed_at: str = ""


@dataclass
class Proxy:
    id: Optional[int] = None
    address: str = ""                        # full proxy URL
    proxy_type: str = "http"                 # http, socks5
    username: str = ""
    password: str = ""
    enabled: bool = True
    assigned_account: str = ""
