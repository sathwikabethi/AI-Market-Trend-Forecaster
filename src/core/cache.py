from __future__ import annotations

import time
from threading import RLock
from typing import Any, Dict


_CACHE: Dict[str, Dict[str, Any]] = {}
_LOCK = RLock()
_HITS = 0
_MISSES = 0


def cache_get(key: str) -> Any:
    global _HITS, _MISSES
    now = time.time()
    with _LOCK:
        item = _CACHE.get(key)
        if not item:
            _MISSES += 1
            return None
        if item["expires_at"] <= now:
            _CACHE.pop(key, None)
            _MISSES += 1
            return None
        _HITS += 1
        return item["value"]


def cache_set(key: str, value: Any, ttl_seconds: int = 60) -> None:
    with _LOCK:
        _CACHE[key] = {
            "value": value,
            "expires_at": time.time() + max(1, int(ttl_seconds)),
        }


def cache_invalidate_prefix(prefix: str) -> None:
    with _LOCK:
        keys = [k for k in _CACHE if k.startswith(prefix)]
        for key in keys:
            _CACHE.pop(key, None)


def cache_stats() -> Dict[str, int]:
    with _LOCK:
        return {
            "size": len(_CACHE),
            "hits": _HITS,
            "misses": _MISSES,
        }
