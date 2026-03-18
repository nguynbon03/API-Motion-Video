"""Multi-account pool with credit-based rotation."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .auth import generate_token
from .client import AuthError, KlingClient, RateLimitError
from .config import Config

log = logging.getLogger(__name__)

# Estimated credit costs by mode
COST_TABLE = {
    "std": 1.0,
    "pro": 1.6,
}


class NoCreditsError(Exception):
    pass


class AllAccountsFailedError(Exception):
    pass


class AccountPool:
    """Manages multiple Kling accounts, auto-selecting the best one per request."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()

    def select_account(self, min_credits: float = 0.0):
        """Pick enabled account with highest remaining credits."""
        candidates = [
            a
            for a in self.config.get_accounts(enabled_only=True)
            if a.credits_remaining > min_credits
        ]
        if not candidates:
            raise NoCreditsError(
                "No accounts with sufficient credits. "
                "Add accounts or refresh credits with: kling-proxy account set-credits"
            )
        return max(candidates, key=lambda a: a.credits_remaining)

    def create_motion_task(
        self,
        payload: Dict[str, Any],
        cost_override: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Create a motion task using the best available account.

        Automatically retries with next account on auth failure.
        """
        mode = payload.get("mode", "std")
        estimated_cost = cost_override if cost_override is not None else COST_TABLE.get(mode, 1.0)

        tried = set()
        last_error = None

        while True:
            try:
                account = self.select_account(min_credits=estimated_cost)
            except NoCreditsError:
                if last_error:
                    raise AllAccountsFailedError(
                        f"All viable accounts failed. Last error: {last_error}"
                    )
                raise

            if account.name in tried:
                raise AllAccountsFailedError(
                    f"All viable accounts exhausted ({len(tried)} tried). "
                    f"Last error: {last_error}"
                )
            tried.add(account.name)

            secret = self.config.decrypt_secret(account)
            token = generate_token(account.access_key, secret)

            log.info("Using account '%s' (credits: %.1f)", account.name, account.credits_remaining)

            try:
                with KlingClient(token) as client:
                    result = client.create_motion_task(payload)
            except AuthError as e:
                log.warning("Account '%s' auth failed: %s — trying next", account.name, e)
                self.config.toggle_account(account.name, enabled=False)
                last_error = str(e)
                continue
            except RateLimitError as e:
                log.warning("Account '%s' rate limited: %s — trying next", account.name, e)
                last_error = str(e)
                continue

            # Success — deduct credits
            self.config.deduct_credits(account.name, estimated_cost)
            result["_proxy"] = {
                "account": account.name,
                "estimated_cost": estimated_cost,
                "credits_remaining": account.credits_remaining,
            }
            return result

    def get_task(self, task_id: str) -> Dict[str, Any]:
        """Query task status using any available account."""
        account = self.select_account()
        secret = self.config.decrypt_secret(account)
        token = generate_token(account.access_key, secret)
        with KlingClient(token) as client:
            return client.get_task(task_id)

    def list_tasks(self, page: int = 1, page_size: int = 30) -> Dict[str, Any]:
        """List tasks using any available account."""
        account = self.select_account()
        secret = self.config.decrypt_secret(account)
        token = generate_token(account.access_key, secret)
        with KlingClient(token) as client:
            return client.list_tasks(page, page_size)

    def pool_status(self) -> Dict[str, Any]:
        """Get summary of all accounts and total credits."""
        accounts = self.config.get_accounts()
        total_remaining = sum(a.credits_remaining for a in accounts)
        total_used = sum(a.credits_used for a in accounts)
        return {
            "total_accounts": len(accounts),
            "enabled_accounts": sum(1 for a in accounts if a.enabled),
            "total_credits_remaining": total_remaining,
            "total_credits_used": total_used,
            "accounts": [
                {
                    "name": a.name,
                    "enabled": a.enabled,
                    "credits_remaining": a.credits_remaining,
                    "credits_used": a.credits_used,
                }
                for a in accounts
            ],
        }
