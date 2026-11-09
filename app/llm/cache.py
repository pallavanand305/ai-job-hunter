from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.config import settings


def _cache_root() -> Path:
    return settings.data_dir / "llm_cache"


def key_for(kind: str, *parts: str) -> str:
    digest = hashlib.sha256()
    digest.update(kind.encode("utf-8"))
    for part in parts:
        digest.update(b"\x00")
        digest.update((part or "").encode("utf-8"))
    return digest.hexdigest()


def get(kind: str, *parts: str) -> Any | None:
    if not settings.llm_cache_enabled:
        return None
    path = _cache_root() / f"{key_for(kind, *parts)}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def set(kind: str, value: Any, *parts: str) -> None:
    if not settings.llm_cache_enabled:
        return
    root = _cache_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{key_for(kind, *parts)}.json"
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _value(source: Any, key: str, default: Any = "") -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def resume_version(profile: Any) -> str:
    digest = hashlib.sha256()
    for value in (
        _value(profile, "resume_text", "") or "",
        json.dumps(_value(profile, "skills", []) or [], sort_keys=True),
        json.dumps(_value(profile, "experience", []) or [], sort_keys=True),
        json.dumps(_value(profile, "projects", []) or [], sort_keys=True),
    ):
        digest.update((value or "").encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()
