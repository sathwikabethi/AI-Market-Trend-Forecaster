from __future__ import annotations

from collections import defaultdict
from threading import RLock
from typing import Dict


_COUNTERS: Dict[str, int] = defaultdict(int)
_TIMINGS: Dict[str, float] = defaultdict(float)
_LOCK = RLock()


def increment(metric: str, value: int = 1) -> None:
    with _LOCK:
        _COUNTERS[metric] += int(value)


def observe_duration(metric: str, milliseconds: float) -> None:
    with _LOCK:
        _TIMINGS[metric] += float(milliseconds)


def metrics_snapshot() -> Dict[str, Dict[str, float]]:
    with _LOCK:
        return {
            "counters": dict(_COUNTERS),
            "timings_ms_total": dict(_TIMINGS),
        }
