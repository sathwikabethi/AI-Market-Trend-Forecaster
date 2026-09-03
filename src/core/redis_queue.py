from __future__ import annotations

from threading import RLock

from src.core.settings import settings

try:
    import redis
except Exception:
    redis = None


_CLIENT = None
_LOCK = RLock()


def _client():
    global _CLIENT
    if not settings.redis_url or redis is None:
        return None
    with _LOCK:
        if _CLIENT is not None:
            return _CLIENT
        try:
            _CLIENT = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        except Exception:
            _CLIENT = None
        return _CLIENT


def redis_available() -> bool:
    client = _client()
    if client is None:
        return False
    try:
        client.ping()
        return True
    except Exception:
        return False


def enqueue_job(job_id: str) -> bool:
    client = _client()
    if client is None:
        return False
    try:
        client.rpush(settings.redis_job_queue_name, job_id)
        return True
    except Exception:
        return False


def dequeue_job(timeout_seconds: int = 1) -> str | None:
    client = _client()
    if client is None:
        return None
    try:
        item = client.blpop(settings.redis_job_queue_name, timeout=max(1, int(timeout_seconds)))
    except Exception:
        return None
    if not item:
        return None
    return str(item[1])


def queue_depth() -> int:
    client = _client()
    if client is None:
        return 0
    try:
        return int(client.llen(settings.redis_job_queue_name))
    except Exception:
        return 0

