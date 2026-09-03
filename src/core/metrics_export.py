from __future__ import annotations

from src.core.cache import cache_stats
from src.core.metrics import metrics_snapshot
from src.core.rate_limit import rate_limit_snapshot
from src.core.redis_queue import queue_depth, redis_available


def prometheus_metrics() -> str:
    snap = metrics_snapshot()
    cache = cache_stats()
    rate = rate_limit_snapshot()

    lines: list[str] = []
    lines.append("# TYPE app_counter_total counter")
    for key, value in snap.get("counters", {}).items():
        lines.append(f'app_counter_total{{name="{key}"}} {int(value)}')

    lines.append("# TYPE app_timing_ms_total counter")
    for key, value in snap.get("timings_ms_total", {}).items():
        lines.append(f'app_timing_ms_total{{name="{key}"}} {float(value)}')

    lines.append("# TYPE app_cache_size gauge")
    lines.append(f'app_cache_size {int(cache.get("size", 0))}')
    lines.append("# TYPE app_cache_hits_total counter")
    lines.append(f'app_cache_hits_total {int(cache.get("hits", 0))}')
    lines.append("# TYPE app_cache_misses_total counter")
    lines.append(f'app_cache_misses_total {int(cache.get("misses", 0))}')

    lines.append("# TYPE app_rate_limit_keys gauge")
    lines.append(f'app_rate_limit_keys {int(rate.get("tracked_keys", 0))}')

    lines.append("# TYPE app_queue_redis_enabled gauge")
    lines.append(f'app_queue_redis_enabled {1 if redis_available() else 0}')
    lines.append("# TYPE app_queue_redis_depth gauge")
    lines.append(f'app_queue_redis_depth {int(queue_depth())}')

    return "\n".join(lines) + "\n"
