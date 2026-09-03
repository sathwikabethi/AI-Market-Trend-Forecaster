from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Dict, List

from sqlalchemy import desc, select

from src.core.database import IngestionRun, now_utc_iso, session_scope
from src.core.jobs import submit_ingestion_job


_SCHEDULER_STARTED = False
_SCHEDULER_LOCK = threading.RLock()


def _record_ingestion_run(run_id: str, source: str, status: str, details: Dict[str, Any] | None = None) -> None:
    with session_scope() as session:
        session.add(
            IngestionRun(
                run_id=run_id,
                source=source,
                status=status,
                started_at=now_utc_iso(),
                completed_at=now_utc_iso() if status in {"queued", "failed"} else None,
                details=json.dumps(details or {}),
            )
        )


def trigger_ingestion_now(source: str = "manual", batch_size: int = 4, *, connector: str | None = None) -> str:
    run_id = f"ing-{uuid.uuid4().hex[:12]}"
    try:
        job_id = submit_ingestion_job(source=source, batch_size=batch_size, connector=connector)
        _record_ingestion_run(
            run_id=run_id,
            source=source,
            status="queued",
            details={
                "job_id": job_id,
                "batch_size": int(batch_size),
                "connector": connector,
            },
        )
    except Exception as exc:
        _record_ingestion_run(
            run_id=run_id,
            source=source,
            status="failed",
            details={"error": str(exc), "batch_size": int(batch_size)},
        )
        raise
    return run_id


def list_ingestion_runs(limit: int = 50) -> List[Dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            select(IngestionRun).order_by(desc(IngestionRun.id)).limit(max(1, int(limit)))
        ).scalars().all()

    return [
        {
            "id": int(row.id),
            "run_id": row.run_id,
            "source": row.source,
            "status": row.status,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "details": row.details,
        }
        for row in rows
    ]


def _scheduler_loop(interval_seconds: int, batch_size: int) -> None:
    while True:
        try:
            trigger_ingestion_now(source="scheduler", batch_size=batch_size)
        except Exception:
            pass
        time.sleep(max(30, interval_seconds))


def start_ingestion_scheduler() -> None:
    global _SCHEDULER_STARTED
    with _SCHEDULER_LOCK:
        if _SCHEDULER_STARTED:
            return
        enabled = os.environ.get("INGESTION_SCHEDULER_ENABLED", "1") == "1"
        if not enabled:
            _SCHEDULER_STARTED = True
            return
        interval = int(os.environ.get("INGESTION_INTERVAL_SECONDS", "900"))
        batch_size = int(os.environ.get("INGESTION_BATCH_SIZE", "4"))
        thread = threading.Thread(
            target=_scheduler_loop,
            args=(interval, batch_size),
            name="ingestion-scheduler",
            daemon=True,
        )
        thread.start()
        _SCHEDULER_STARTED = True
