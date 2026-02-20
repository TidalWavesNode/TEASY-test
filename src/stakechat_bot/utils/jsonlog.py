from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

import portalocker


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ensure_parent(path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)


def append_jsonl(path: str, event: Dict[str, Any]) -> None:
    ensure_parent(path)
    event = dict(event)
    event.setdefault("ts", now_iso())
    line = json.dumps(event, ensure_ascii=False)
    with portalocker.Lock(path, "a", timeout=5):
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
