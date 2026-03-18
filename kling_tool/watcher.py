"""Auto-import accounts.txt when file changes."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

from . import config as cfg

log = logging.getLogger(__name__)

WATCH_FILE = cfg.ACCOUNTS_DIR / "accounts.txt"


class AccountWatcher:
    """Background thread that watches accounts.txt for changes and auto-imports."""

    def __init__(self, accounts_manager):
        self._mgr = accounts_manager
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_mtime: float = 0
        self._interval = 30  # seconds

    def start(self):
        if self._running:
            return
        self._running = True
        # Import immediately on start
        self._check_and_import()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="account-watcher")
        self._thread.start()
        log.info("Account watcher started (watching %s)", WATCH_FILE)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while self._running:
            time.sleep(self._interval)
            try:
                self._check_and_import()
            except Exception as e:
                log.error("Watcher error: %s", e)

    def _check_and_import(self):
        if not WATCH_FILE.exists():
            return

        mtime = os.path.getmtime(WATCH_FILE)
        if mtime == self._last_mtime:
            return

        self._last_mtime = mtime
        log.info("accounts.txt changed, importing...")

        lines = WATCH_FILE.read_text(encoding="utf-8").splitlines()
        count = self._mgr.add_bulk(lines, default_credits=66.0)
        if count > 0:
            log.info("Imported %d new accounts from accounts.txt", count)
        else:
            log.debug("No new accounts to import")
