from __future__ import annotations

import json
import threading
import time
from datetime import date
from pathlib import Path

from app.config import settings


class RateLimitExceeded(Exception):
    pass


class CallRateLimiter:
    """Persistent, process-local free-tier guard for outbound LLM calls."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (settings.data_dir / "llm_rate.json")
        self._lock = threading.Lock()
        self._state = self._read()

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        today = date.today().isoformat()
        if data.get("date") != today:
            data = {"date": today, "count": 0, "last_call": 0.0}
        return data

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._state), encoding="utf-8")

    def acquire(self) -> None:
        with self._lock:
            self._state = self._read()
            limit = max(0, int(settings.llm_daily_call_limit))
            if limit and self._state.get("count", 0) >= limit:
                raise RateLimitExceeded(f"daily LLM call limit reached ({limit})")
            interval = max(0.0, float(settings.llm_min_interval_seconds))
            elapsed = time.time() - float(self._state.get("last_call", 0.0))
            if interval and elapsed < interval:
                time.sleep(interval - elapsed)
            self._state["count"] = int(self._state.get("count", 0)) + 1
            self._state["last_call"] = time.time()
            self._write()

    def info(self) -> dict:
        self._state = self._read()
        return {
            "date": self._state.get("date"),
            "count": int(self._state.get("count", 0)),
            "daily_limit": int(settings.llm_daily_call_limit),
        }
