from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import RLock
from typing import Deque, Dict


_LOCK = RLock()
_REQUESTS: Dict[str, Deque[float]] = defaultdict(deque)


def allow_request(key: str, max_requests: int, window_seconds: int) -> bool:
    now = time.time()
    with _LOCK:
        queue = _REQUESTS[key]
        while queue and now - queue[0] > window_seconds:
            queue.popleft()
        if len(queue) >= max_requests:
            return False
        queue.append(now)
        return True


def rate_limit_snapshot() -> Dict[str, int]:
    with _LOCK:
        return {"tracked_keys": len(_REQUESTS)}

