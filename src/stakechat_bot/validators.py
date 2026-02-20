from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional

import requests

from .config import ValidatorsConfig


@dataclass
class Delegate:
    name: str
    hotkey: str


class ValidatorResolver:
    """Resolves a validator name -> hotkey ss58.

    - If the input already looks like an ss58 string, we return it.
    - We have a small built-in mapping for the default (tao.bot).
    - Otherwise we fall back to a remote delegate list (cached).
    """

    TAOBOT_HOTKEY = "5E2LP6EnZ54m3wS8s1yPvD5c3xo71kQroBw7aUVK32TKeZ5u"

    def __init__(self, cfg: ValidatorsConfig):
        self.cfg = cfg
        self._cache: Dict[str, str] = {}
        self._cache_at: float = 0.0

    def _refresh(self) -> None:
        now = time.time()
        ttl = max(60, int(self.cfg.cache_ttl_minutes) * 60)
        if self._cache and (now - self._cache_at) < ttl:
            return

        url = self.cfg.delegates_fallback_url
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()

        cache: Dict[str, str] = {}
        # format is: { "hotkey": {"name": ...} ... }
        if isinstance(data, dict):
            for hk, info in data.items():
                name = ""
                if isinstance(info, dict):
                    name = str(info.get("name", "") or "").strip()
                if hk:
                    cache[hk] = hk
                if name:
                    cache[name.lower()] = hk

        self._cache = cache
        self._cache_at = now

    def resolve(self, validator: str) -> Optional[str]:
        """Return hotkey if validator is a hotkey or known delegate name."""
        v = (validator or "").strip()
        if not v:
            return None

        lv = v.lower()
        if lv in {"default", "tao.bot", "taobot", "tao_bot"}:
            return self.TAOBOT_HOTKEY

        # If it looks like an ss58 address, just use it.
        if len(v) >= 40 and not any(ch.isspace() for ch in v):
            return v

        self._refresh()
        return self._cache.get(lv)
