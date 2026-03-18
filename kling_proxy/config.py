"""Account storage with Fernet encryption for secret keys."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from cryptography.fernet import Fernet

CONFIG_DIR = Path.home() / ".kling_proxy"
CONFIG_FILE = CONFIG_DIR / "config.json"
KEY_FILE = CONFIG_DIR / ".key"


@dataclass
class Account:
    name: str
    access_key: str
    secret_key_encrypted: str  # Fernet-encrypted
    credits_remaining: float = 0.0
    credits_used: float = 0.0
    enabled: bool = True
    added_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def decrypt_secret(self, fernet: Fernet) -> str:
        return fernet.decrypt(self.secret_key_encrypted.encode()).decode()


class Config:
    def __init__(self):
        self._ensure_config_dir()
        self._fernet = Fernet(self._load_or_create_key())
        self._accounts: List[Account] = []
        self._load()

    # --- public API ---

    def get_accounts(self, enabled_only: bool = False) -> List[Account]:
        if enabled_only:
            return [a for a in self._accounts if a.enabled]
        return list(self._accounts)

    def get_account(self, name: str) -> Optional[Account]:
        for a in self._accounts:
            if a.name == name:
                return a
        return None

    def add_account(
        self,
        name: str,
        access_key: str,
        secret_key: str,
        credits: float = 0.0,
    ) -> Account:
        if self.get_account(name):
            raise ValueError(f"Account '{name}' already exists")
        encrypted = self._fernet.encrypt(secret_key.encode()).decode()
        account = Account(
            name=name,
            access_key=access_key,
            secret_key_encrypted=encrypted,
            credits_remaining=credits,
        )
        self._accounts.append(account)
        self.save()
        return account

    def remove_account(self, name: str) -> bool:
        before = len(self._accounts)
        self._accounts = [a for a in self._accounts if a.name != name]
        if len(self._accounts) < before:
            self.save()
            return True
        return False

    def update_credits(self, name: str, credits: float) -> bool:
        account = self.get_account(name)
        if not account:
            return False
        account.credits_remaining = credits
        self.save()
        return True

    def deduct_credits(self, name: str, amount: float) -> None:
        account = self.get_account(name)
        if account:
            account.credits_remaining = max(0, account.credits_remaining - amount)
            account.credits_used += amount
            self.save()

    def toggle_account(self, name: str, enabled: bool) -> bool:
        account = self.get_account(name)
        if not account:
            return False
        account.enabled = enabled
        self.save()
        return True

    def decrypt_secret(self, account: Account) -> str:
        return account.decrypt_secret(self._fernet)

    def save(self) -> None:
        data = {"accounts": [asdict(a) for a in self._accounts]}
        CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- internals ---

    def _ensure_config_dir(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def _load_or_create_key(self) -> bytes:
        if KEY_FILE.exists():
            return KEY_FILE.read_bytes().strip()
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
        # Best-effort permissions (Unix only)
        if sys.platform != "win32":
            os.chmod(KEY_FILE, 0o600)
        return key

    def _load(self) -> None:
        if not CONFIG_FILE.exists():
            self._accounts = []
            return
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        self._accounts = [Account(**a) for a in raw.get("accounts", [])]
