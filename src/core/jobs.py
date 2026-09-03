from __future__ import annotations

import json
import os
import random
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import asc, func, select

from src.analytics.business_metrics import compute_business_kpis
from src.core.database import Job, now_utc_iso, session_scope
from src.core.redis_queue import dequeue_job, enqueue_job, redis_available, queue_depth
from src.data_processing import append_review
from src.data_processing.connectors import ingest_reviews
from src.nlp.aspect_sentiment import aspect_sentiment_analysis


_WORKER_STARTED = False
_WORKER_LOCK = threading.RLock()


def _rating_from_aspects(aspects: Dict[str, Dict[str, Any]]) -> int:
    pos = 0.0
    neg = 0.0
    n = 0
    for result in aspects.values():
        if not isinstance(result, dict):
            continue
        scores = result.get("scores", {})
        if not isinstance(scores, dict):
            continue
        pos += float(scores.get("positive", 0.0) or 0.0)
        neg += float(scores.get("negative", 0.0) or 0.0)
        n += 1
    if n == 0:
        return 3
    delta = (pos - neg) / n
    if delta >= 0.25:
        return 5
    if delta >= 0.08:
        return 4
    if delta <= -0.25:
        return 1
    if delta <= -0.08:
        return 2
    return 3


def _create_job(job_type: str, payload: Dict[str, Any], status: str = "pending") -> str:
    return _create_job_v2(job_type=job_type, payload=payload, status=status)


def _create_job_v2(
    *,
    job_type: str,
    payload: Dict[str, Any],
    status: str = "pending",
    idempotency_key: str | None = None,
    max_attempts: int = 3,
    available_at: str | None = None,
) -> str:
    job_id = f"job-{uuid.uuid4().hex[:12]}"
    safe_key = (idempotency_key or "").strip() or None
    safe_max_attempts = max(1, min(int(max_attempts or 3), 10))
    created_at = now_utc_iso()
    available_at_value = str(available_at or created_at)
    with session_scope() as session:
        if safe_key:
            existing = session.execute(
                select(Job).where(Job.idempotency_key == safe_key)
            ).scalar_one_or_none()
            if existing:
                # Best-effort to wake the worker if the job is still pending.
                if existing.status == "pending":
                    enqueue_job(existing.job_id)
                return str(existing.job_id)

        session.add(
            Job(
                job_id=job_id,
                job_type=job_type,
                status=status,
                idempotency_key=safe_key,
                payload=json.dumps(payload),
                attempts=0,
                max_attempts=safe_max_attempts,
                available_at=available_at_value,
                created_at=created_at,
            )
        )
    if status == "pending" and available_at_value <= created_at:
        enqueue_job(job_id)
    return job_id


def submit_analyze_job(
    text: str,
    product: str,
    requested_by: str | None = None,
    *,
    idempotency_key: str | None = None,
) -> str:
    payload = {"text": text, "product": product, "requested_by": requested_by}
    return _create_job_v2(job_type="analyze_review", payload=payload, idempotency_key=idempotency_key)


def submit_ingestion_job(source: str = "scheduler", batch_size: int = 4, *, connector: str | None = None) -> str:
    payload = {"source": source, "batch_size": int(max(1, batch_size))}
    if connector:
        payload["connector"] = str(connector)
    return _create_job("ingest_reviews", payload=payload)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with session_scope() as session:
        row = session.execute(
            select(Job).where(Job.job_id == job_id)
        ).scalar_one_or_none()
    if not row:
        return None
    return {
        "job_id": row.job_id,
        "job_type": row.job_type,
        "status": row.status,
        "idempotency_key": row.idempotency_key,
        "payload": row.payload,
        "attempts": int(row.attempts or 0),
        "max_attempts": int(row.max_attempts or 0),
        "available_at": row.available_at,
        "result": row.result,
        "dead_letter_reason": row.dead_letter_reason,
        "error": row.error,
        "created_at": row.created_at,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
    }


def _next_pending_job() -> Optional[Dict[str, Any]]:
    now = now_utc_iso()
    with session_scope() as session:
        row = session.execute(
            select(Job)
            .where(
                Job.status == "pending",
                Job.available_at <= now,
            )
            .order_by(asc(Job.available_at), asc(Job.created_at))
            .limit(1)
        ).scalar_one_or_none()
        if not row:
            return None
        row.status = "running"
        row.started_at = now
        row.attempts = int(row.attempts or 0) + 1
        payload = {
            "job_id": row.job_id,
            "job_type": row.job_type,
            "payload": row.payload,
        }
        return payload


def _take_job_by_id(job_id: str) -> Optional[Dict[str, Any]]:
    now = now_utc_iso()
    with session_scope() as session:
        row = session.execute(
            select(Job).where(
                Job.job_id == job_id,
                Job.status == "pending",
                Job.available_at <= now,
            )
        ).scalar_one_or_none()
        if not row:
            return None
        row.status = "running"
        row.started_at = now
        row.attempts = int(row.attempts or 0) + 1
        return {
            "job_id": row.job_id,
            "job_type": row.job_type,
            "payload": row.payload,
        }


def _complete_job(job_id: str, result: Dict[str, Any]) -> None:
    with session_scope() as session:
        row = session.execute(
            select(Job).where(Job.job_id == job_id)
        ).scalar_one_or_none()
        if not row:
            return
        row.status = "completed"
        row.result = json.dumps(result)
        row.completed_at = now_utc_iso()


def _retry_delay_seconds(attempt: int) -> int:
    # attempt is 1-based (first execution attempt = 1)
    base = min(60, int(2 ** max(0, attempt - 1)))
    jitter = random.randint(0, max(1, base // 2))
    return int(min(300, base + jitter))


def _handle_job_failure(job_id: str, error: str) -> None:
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat(timespec="seconds")
    with session_scope() as session:
        row = session.execute(select(Job).where(Job.job_id == job_id)).scalar_one_or_none()
        if not row:
            return
        row.error = (error or "job_failed")[:4000]
        attempts = int(row.attempts or 0)
        max_attempts = int(row.max_attempts or 3)

        non_retriable = "Unsupported job type:" in row.error
        if non_retriable:
            row.status = "dead"
            row.dead_letter_reason = "unsupported_job_type"
            row.completed_at = now_iso
            return

        if attempts < max_attempts:
            delay = _retry_delay_seconds(attempts)
            row.status = "pending"
            row.available_at = (now_dt + timedelta(seconds=delay)).isoformat(timespec="seconds")
            # Don't enqueue delayed retries into Redis; DB polling handles scheduling reliably.
            row.completed_at = None
            return

        row.status = "dead"
        row.dead_letter_reason = "max_attempts_exceeded"
        row.completed_at = now_iso


def _process_analyze_job(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = json.loads(job.get("payload") or "{}")
    text = str(payload.get("text", ""))
    product = str(payload.get("product", "general") or "general")
    aspects = aspect_sentiment_analysis(text)
    kpis = compute_business_kpis(aspects)
    rating = _rating_from_aspects(aspects)
    append_review(text=text, product=product, source="job_worker", rating=rating)
    return {"aspects": aspects, "business_kpis": kpis}


def _process_ingest_job(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = json.loads(job.get("payload") or "{}")
    batch_size = int(payload.get("batch_size", 4) or 4)
    source = str(payload.get("source", "scheduler"))
    connector = payload.get("connector")
    result = ingest_reviews(
        source=str(source),
        batch_size=int(max(1, batch_size)),
        connector=str(connector) if connector else None,
    )
    result["source"] = source
    return result


def _process_job(job: Dict[str, Any]) -> Dict[str, Any]:
    job_type = str(job.get("job_type", ""))
    if job_type == "analyze_review":
        return _process_analyze_job(job)
    if job_type == "ingest_reviews":
        return _process_ingest_job(job)
    raise RuntimeError(f"Unsupported job type: {job_type}")


def _worker_loop(poll_seconds: float = 1.0) -> None:
    while True:
        job = None
        if redis_available():
            queued_job_id = dequeue_job(timeout_seconds=max(1, int(poll_seconds)))
            if queued_job_id:
                job = _take_job_by_id(str(queued_job_id))
        if job is None:
            job = _next_pending_job()
        if not job:
            time.sleep(poll_seconds)
            continue
        try:
            result = _process_job(job)
            _complete_job(job["job_id"], result)
        except Exception as exc:
            _handle_job_failure(job["job_id"], str(exc))


def start_job_worker() -> None:
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        enabled = os.environ.get("JOB_WORKER_ENABLED", "1") == "1"
        if not enabled:
            _WORKER_STARTED = True
            return
        thread = threading.Thread(target=_worker_loop, name="job-worker", daemon=True)
        thread.start()
        _WORKER_STARTED = True


def queue_stats() -> Dict[str, Any]:
    now = now_utc_iso()
    with session_scope() as session:
        pending_total = int(
            session.execute(select(func.count()).select_from(Job).where(Job.status == "pending")).scalar_one()
            or 0
        )
        pending_ready = int(
            session.execute(
                select(func.count())
                .select_from(Job)
                .where(Job.status == "pending", Job.available_at <= now)
            ).scalar_one()
            or 0
        )
        dead_total = int(
            session.execute(select(func.count()).select_from(Job).where(Job.status == "dead")).scalar_one()
            or 0
        )
    return {
        "redis_enabled": redis_available(),
        "redis_depth": queue_depth(),
        "db_pending_total": pending_total,
        "db_pending_ready": pending_ready,
        "db_dead_total": dead_total,
    }
