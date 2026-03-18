"""Account pool manager — rotation, proxy assignment, credit tracking."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .config import MAX_CONCURRENT_PER_ACCOUNT
from .database import Database
from .models import Account, AccountStatus, _now

log = logging.getLogger(__name__)


class NoAvailableAccountError(Exception):
    pass


class AccountManager:
    """Manages the pool of Kling web accounts with proxy rotation."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    # ── CRUD ─────────────────────────────────────────────────

    def add(
        self,
        name: str,
        email: str,
        password: str,
        proxy: str = "",
        credits: float = 0.0,
        note: str = "",
    ) -> int:
        acc = Account(
            name=name,
            email=email,
            password=password,
            proxy=proxy,
            credits_remaining=credits,
            note=note,
        )
        row_id = self.db.add_account(acc)
        log.info("Account added: %s (email: %s)", name, email)
        return row_id

    def add_bulk(self, lines: List[str], default_credits: float = 66.0) -> int:
        """Add accounts from text lines. Supports formats:
        - email:password
        - email:password:proxy
        - name|email|password|proxy|credits
        """
        count = 0
        for i, line in enumerate(lines):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("|") if "|" in line else None
            if parts and len(parts) >= 3:
                name = parts[0].strip()
                email = parts[1].strip()
                password = parts[2].strip()
                proxy = parts[3].strip() if len(parts) > 3 else ""
                credits = float(parts[4].strip()) if len(parts) > 4 else default_credits
            else:
                # email:password or email:password:proxy
                parts = line.split(":")
                if len(parts) < 2:
                    log.warning("Skip invalid line %d: %s", i + 1, line[:30])
                    continue
                email = parts[0].strip()
                password = parts[1].strip()
                proxy = parts[2].strip() if len(parts) > 2 else ""
                credits = default_credits
                name = email.split("@")[0]

            try:
                self.add(name, email, password, proxy, credits)
                count += 1
            except Exception as e:
                log.warning("Failed to add %s: %s", name, e)

        return count

    def remove(self, name: str) -> bool:
        return self.db.delete_account(name)

    def list_all(self) -> List[Dict]:
        return self.db.get_all_accounts()

    def get(self, name: str) -> Optional[Dict]:
        return self.db.get_account(name)

    # ── Rotation ─────────────────────────────────────────────

    def select_best(self) -> Dict:
        """Select the best available account for a new task.

        Priority: active status → highest credits → least recent usage → fewest active tasks.
        """
        accounts = self.db.get_active_accounts()
        if not accounts:
            raise NoAvailableAccountError(
                "No active accounts with credits available. "
                "Add accounts: kling-tool account add ..."
            )

        # Filter out accounts with too many concurrent tasks
        candidates = []
        for acc in accounts:
            active_count = self.db.count_active_tasks(acc["name"])
            if active_count < MAX_CONCURRENT_PER_ACCOUNT:
                acc["_active_tasks"] = active_count
                candidates.append(acc)

        if not candidates:
            raise NoAvailableAccountError(
                f"All {len(accounts)} active accounts are busy "
                f"(max {MAX_CONCURRENT_PER_ACCOUNT} concurrent tasks each). "
                "Wait or add more accounts."
            )

        # Sort: most credits first, then least recently used
        candidates.sort(key=lambda a: (-a["credits_remaining"], a.get("last_used_at", "")))

        selected = candidates[0]
        log.info(
            "Selected account '%s' (credits: %.1f, active tasks: %d)",
            selected["name"],
            selected["credits_remaining"],
            selected.get("_active_tasks", 0),
        )
        return selected

    def mark_used(self, name: str, cost: float = 1.0):
        """Mark account as just used and deduct credits."""
        self.db.update_account(
            name,
            last_used_at=_now(),
            credits_remaining=max(0, (self.get(name) or {}).get("credits_remaining", 0) - cost),
            credits_used=(self.get(name) or {}).get("credits_used", 0) + cost,
        )

    def set_credits(self, name: str, credits: float) -> bool:
        return self.db.update_account(name, credits_remaining=credits)

    def set_status(self, name: str, status: AccountStatus) -> bool:
        return self.db.update_account(name, status=status.value)

    # ── Stats ────────────────────────────────────────────────

    def pool_stats(self) -> Dict:
        accounts = self.db.get_all_accounts()
        active = [a for a in accounts if a["status"] == AccountStatus.ACTIVE.value]
        return {
            "total_accounts": len(accounts),
            "active_accounts": len(active),
            "disabled_accounts": len(accounts) - len(active),
            "total_credits_remaining": sum(a["credits_remaining"] for a in accounts),
            "total_credits_used": sum(a["credits_used"] for a in accounts),
            "accounts": [
                {
                    "name": a["name"],
                    "email": a["email"],
                    "status": a["status"],
                    "credits_remaining": a["credits_remaining"],
                    "credits_used": a["credits_used"],
                    "proxy": a["proxy"] or "(direct)",
                    "last_used": a["last_used_at"] or "never",
                }
                for a in accounts
            ],
        }
