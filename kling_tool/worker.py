"""Background worker — processes task queue, handles video generation lifecycle."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from .accounts import AccountManager, NoAvailableAccountError
from .browser import KlingBrowser
from .config import OUTPUTS_DIR, POLL_INTERVAL
from .database import Database
from .models import AccountStatus, Task, TaskStatus

log = logging.getLogger(__name__)


class Worker:
    """Background worker that processes queued tasks using the account pool."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.accounts = AccountManager(self.db)
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start the worker in a background thread."""
        if self._running:
            log.warning("Worker already running")
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="kling-worker")
        self._thread.start()
        log.info("Worker started")

    def stop(self):
        """Stop the worker."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=120)  # Long timeout for Docker SIGTERM
        log.info("Worker stopped")

    def is_running(self) -> bool:
        return self._running

    def process_one(self) -> bool:
        """Process a single queued task. Returns True if a task was processed."""
        # Get next queued task
        queued = self.db.get_tasks(status=TaskStatus.QUEUED.value, page=1, size=1)
        if not queued:
            return False

        task = queued[0]
        task_id = task["id"]
        log.info("Processing task #%d...", task_id)

        # Select account
        try:
            account = self.accounts.select_best()
        except NoAvailableAccountError as e:
            log.warning("No account available: %s", e)
            return False

        account_name = account["name"]
        self.db.update_task(task_id, status=TaskStatus.SUBMITTED.value, account_name=account_name)

        # Run browser automation
        browser = KlingBrowser(
            account_name=account_name,
            proxy=account.get("proxy") or None,
        )

        try:
            with browser:
                # Login if needed
                if not browser._is_logged_in():
                    success = browser.login(account["email"], account["password"])
                    if not success:
                        self.db.update_task(
                            task_id,
                            status=TaskStatus.FAILED.value,
                            error_message="Login failed",
                        )
                        self.accounts.set_status(account_name, AccountStatus.DISABLED)
                        return True

                # Create motion task
                self.db.update_task(task_id, status=TaskStatus.PROCESSING.value)

                result = browser.create_motion_task(
                    image_path=task["image_url"],
                    video_path=task["video_url"],
                    prompt=task.get("prompt", ""),
                    mode=task.get("mode", "pro"),
                    model_name=task.get("model_name", "kling-v2-6"),
                    character_orientation=task.get("character_orientation", "image"),
                    keep_original_sound=task.get("keep_original_sound", "yes"),
                )

                if result.get("success"):
                    kling_task_id = result.get("task_id", "")
                    self.db.update_task(
                        task_id,
                        status=TaskStatus.PROCESSING.value,
                        kling_task_id=kling_task_id,
                    )
                    self.accounts.mark_used(account_name, cost=1.0)

                    # Poll for completion
                    self._poll_completion(browser, task_id, kling_task_id)
                else:
                    self.db.update_task(
                        task_id,
                        status=TaskStatus.FAILED.value,
                        error_message=result.get("error", "Unknown error"),
                    )

                # Log intercepted APIs for future optimization
                apis = browser.get_intercepted_apis()
                if apis:
                    log.info("Intercepted %d internal API calls (for future HTTP-only mode)", len(apis))
                    for api in apis[:5]:
                        log.debug("  %s %s", api["method"], api["url"])

        except Exception as e:
            log.error("Task #%d failed: %s", task_id, e)
            self.db.update_task(
                task_id,
                status=TaskStatus.FAILED.value,
                error_message=str(e),
            )

        return True

    def _poll_completion(self, browser: KlingBrowser, task_id: int, kling_task_id: str):
        """Poll task status until completion or timeout."""
        max_polls = 60  # 60 * 10s = 10 minutes
        for i in range(max_polls):
            if not self._running:
                break

            time.sleep(POLL_INTERVAL)

            status = browser.check_task_status(kling_task_id)
            log.info("Task #%d poll %d: %s", task_id, i + 1, status.get("status"))

            if status["status"] == "succeed":
                # Download video to local outputs
                video_url = status.get("video_url", "")
                local_path = str(OUTPUTS_DIR / f"task_{task_id}.mp4")
                downloaded = browser.download_video(local_path)
                result_url = f"/outputs/task_{task_id}.mp4" if downloaded else video_url

                self.db.update_task(
                    task_id,
                    status=TaskStatus.SUCCEED.value,
                    result_video_url=result_url,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
                log.info("Task #%d completed! Video: %s", task_id, result_url)
                return

            if status["status"] == "failed":
                self.db.update_task(
                    task_id,
                    status=TaskStatus.FAILED.value,
                    error_message=status.get("error", "Generation failed"),
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
                return

        # Timeout
        log.warning("Task #%d timed out after polling", task_id)
        self.db.update_task(
            task_id,
            status=TaskStatus.FAILED.value,
            error_message="Polling timeout",
        )

    def _loop(self):
        """Main worker loop."""
        while self._running:
            try:
                processed = self.process_one()
                if not processed:
                    time.sleep(5)  # No tasks, wait before checking again
            except Exception as e:
                log.error("Worker loop error: %s", e)
                time.sleep(10)
