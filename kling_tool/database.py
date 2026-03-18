"""SQLite database for accounts, tasks, and proxies."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Dict, List, Optional

from .config import DB_PATH, ensure_dirs
from .models import Account, AccountStatus, Task, TaskStatus


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


class Database:
    def __init__(self, db_path=None):
        ensure_dirs()
        self._path = str(db_path or DB_PATH)
        self._init_tables()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self._path)
        conn.row_factory = _dict_factory
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_tables(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    email TEXT NOT NULL,
                    password TEXT NOT NULL,
                    proxy TEXT DEFAULT '',
                    cookies_file TEXT DEFAULT '',
                    credits_remaining REAL DEFAULT 0,
                    credits_used REAL DEFAULT 0,
                    status TEXT DEFAULT 'active',
                    last_used_at TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    note TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    external_task_id TEXT DEFAULT '',
                    account_name TEXT DEFAULT '',
                    image_url TEXT NOT NULL,
                    video_url TEXT NOT NULL,
                    prompt TEXT DEFAULT '',
                    model_name TEXT DEFAULT 'kling-v2-6',
                    mode TEXT DEFAULT 'pro',
                    character_orientation TEXT DEFAULT 'image',
                    keep_original_sound TEXT DEFAULT 'yes',
                    status TEXT DEFAULT 'queued',
                    result_video_url TEXT DEFAULT '',
                    result_watermark_url TEXT DEFAULT '',
                    duration REAL DEFAULT 0,
                    error_message TEXT DEFAULT '',
                    kling_task_id TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    completed_at TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS proxies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    address TEXT UNIQUE NOT NULL,
                    proxy_type TEXT DEFAULT 'http',
                    username TEXT DEFAULT '',
                    password TEXT DEFAULT '',
                    enabled INTEGER DEFAULT 1,
                    assigned_account TEXT DEFAULT ''
                );
            """)

    # ── Accounts ─────────────────────────────────────────────

    def add_account(self, acc: Account) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO accounts (name, email, password, proxy, cookies_file,
                   credits_remaining, credits_used, status, last_used_at, created_at, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (acc.name, acc.email, acc.password, acc.proxy, acc.cookies_file,
                 acc.credits_remaining, acc.credits_used, acc.status,
                 acc.last_used_at, acc.created_at, acc.note),
            )
            return cur.lastrowid

    def get_account(self, name: str) -> Optional[Dict]:
        with self._conn() as conn:
            cur = conn.execute("SELECT * FROM accounts WHERE name = ?", (name,))
            return cur.fetchone()

    def get_all_accounts(self) -> List[Dict]:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM accounts ORDER BY credits_remaining DESC").fetchall()

    def get_active_accounts(self) -> List[Dict]:
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM accounts WHERE status = ? AND credits_remaining > 0 ORDER BY credits_remaining DESC",
                (AccountStatus.ACTIVE.value,),
            ).fetchall()

    def update_account(self, name: str, **fields) -> bool:
        if not fields:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [name]
        with self._conn() as conn:
            cur = conn.execute(f"UPDATE accounts SET {set_clause} WHERE name = ?", values)
            return cur.rowcount > 0

    def delete_account(self, name: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM accounts WHERE name = ?", (name,))
            return cur.rowcount > 0

    # ── Tasks ────────────────────────────────────────────────

    def add_task(self, task: Task) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO tasks (external_task_id, account_name, image_url, video_url,
                   prompt, model_name, mode, character_orientation, keep_original_sound,
                   status, result_video_url, result_watermark_url, duration,
                   error_message, kling_task_id, created_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task.external_task_id, task.account_name, task.image_url, task.video_url,
                 task.prompt, task.model_name, task.mode, task.character_orientation,
                 task.keep_original_sound, task.status, task.result_video_url,
                 task.result_watermark_url, task.duration, task.error_message,
                 task.kling_task_id, task.created_at, task.completed_at),
            )
            return cur.lastrowid

    def get_task(self, task_id: int) -> Optional[Dict]:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()

    def get_task_by_external_id(self, ext_id: str) -> Optional[Dict]:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM tasks WHERE external_task_id = ?", (ext_id,)).fetchone()

    def get_tasks(self, status: Optional[str] = None, page: int = 1, size: int = 30) -> List[Dict]:
        offset = (page - 1) * size
        with self._conn() as conn:
            if status:
                return conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                    (status, size, offset),
                ).fetchall()
            return conn.execute(
                "SELECT * FROM tasks ORDER BY id DESC LIMIT ? OFFSET ?",
                (size, offset),
            ).fetchall()

    def update_task(self, task_id: int, **fields) -> bool:
        if not fields:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [task_id]
        with self._conn() as conn:
            cur = conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
            return cur.rowcount > 0

    def count_active_tasks(self, account_name: str) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) as cnt FROM tasks WHERE account_name = ? AND status IN (?, ?)",
                (account_name, TaskStatus.SUBMITTED.value, TaskStatus.PROCESSING.value),
            )
            return cur.fetchone()["cnt"]

    # ── Proxies ──────────────────────────────────────────────

    def add_proxy(self, address: str, proxy_type: str = "http", username: str = "", password: str = "") -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO proxies (address, proxy_type, username, password) VALUES (?, ?, ?, ?)",
                (address, proxy_type, username, password),
            )
            return cur.lastrowid

    def get_available_proxies(self) -> List[Dict]:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM proxies WHERE enabled = 1").fetchall()

    def assign_proxy(self, proxy_id: int, account_name: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE proxies SET assigned_account = ? WHERE id = ?",
                (account_name, proxy_id),
            )
            return cur.rowcount > 0
