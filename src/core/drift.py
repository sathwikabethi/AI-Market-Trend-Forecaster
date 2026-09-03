from __future__ import annotations

import json
import math
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, cast

import pandas as pd
from sqlalchemy import desc, select

from src.core.alerts import _persist_alert
from src.core.database import ModelDriftRun, now_utc_iso, session_scope
from src.data_processing.review_store import PROCESSED_DATA_PATH, initialize_datasets


def _safe_float(value: object) -> float:
    try:
        return float(cast(Any, value))
    except Exception:
        return 0.0


def _kl_divergence(p: List[float], q: List[float]) -> float:
    total = 0.0
    for pi, qi in zip(p, q):
        if pi <= 0.0 or qi <= 0.0:
            continue
        total += pi * math.log(pi / qi)
    return float(total)


def _js_divergence(p: List[float], q: List[float]) -> float:
    m = [(pi + qi) / 2.0 for pi, qi in zip(p, q)]
    return 0.5 * _kl_divergence(p, m) + 0.5 * _kl_divergence(q, m)


def run_drift_detection(model_name: str = "nlp_baseline") -> Dict[str, Any]:
    initialize_datasets()
    recent_days = max(7, int(os.environ.get("DRIFT_RECENT_DAYS", "30") or 30))
    baseline_days = max(14, int(os.environ.get("DRIFT_BASELINE_DAYS", "90") or 90))
    threshold = _safe_float(os.environ.get("DRIFT_THRESHOLD", "0.25"))

    run_id = f"drift-{uuid.uuid4().hex[:12]}"
    created_at = now_utc_iso()

    if not PROCESSED_DATA_PATH.exists():
        result = {
            "run_id": run_id,
            "created_at": created_at,
            "model_name": model_name,
            "status": "no_data",
            "metric": "js_divergence",
            "drift_score": 0.0,
            "baseline_window": None,
            "recent_window": None,
            "details": {"reason": "processed_dataset_missing"},
        }
        _persist_run(result)
        return result

    df = pd.read_csv(PROCESSED_DATA_PATH)
    if df.empty or "date" not in df.columns:
        result = {
            "run_id": run_id,
            "created_at": created_at,
            "model_name": model_name,
            "status": "no_data",
            "metric": "js_divergence",
            "drift_score": 0.0,
            "baseline_window": None,
            "recent_window": None,
            "details": {"reason": "empty_dataset_or_missing_date"},
        }
        _persist_run(result)
        return result

    df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True)
    df = df.dropna(subset=["date"])
    if df.empty:
        result = {
            "run_id": run_id,
            "created_at": created_at,
            "model_name": model_name,
            "status": "no_data",
            "metric": "js_divergence",
            "drift_score": 0.0,
            "baseline_window": None,
            "recent_window": None,
            "details": {"reason": "no_valid_dates"},
        }
        _persist_run(result)
        return result

    # Use dataset max date as the evaluation anchor to avoid relying on wall clock.
    end_dt = df["date"].max().to_pydatetime()
    recent_start = end_dt - timedelta(days=recent_days)
    baseline_end = recent_start
    baseline_start = baseline_end - timedelta(days=baseline_days)

    baseline_df = df[(df["date"] >= baseline_start) & (df["date"] < baseline_end)]
    recent_df = df[(df["date"] >= recent_start) & (df["date"] <= end_dt)]

    labels = ["negative", "neutral", "positive"]
    def _dist(frame: pd.DataFrame) -> List[float]:
        if frame.empty or "sentiment_label" not in frame.columns:
            return [1 / 3, 1 / 3, 1 / 3]
        counts = frame["sentiment_label"].fillna("neutral").astype(str).str.lower().value_counts()
        total = max(1, int(len(frame)))
        return [float(counts.get(label, 0)) / total for label in labels]

    p = _dist(baseline_df)
    q = _dist(recent_df)
    js = _js_divergence(p, q)

    baseline_mean = (
        float(pd.to_numeric(baseline_df["sentiment_score"], errors="coerce").mean() or 0.0)
        if (not baseline_df.empty and "sentiment_score" in baseline_df.columns)
        else 0.0
    )
    recent_mean = (
        float(pd.to_numeric(recent_df["sentiment_score"], errors="coerce").mean() or 0.0)
        if (not recent_df.empty and "sentiment_score" in recent_df.columns)
        else 0.0
    )

    drift_score = float(max(0.0, min(1.0, js)))
    status = "ok" if drift_score < threshold else "drift_detected"

    details = {
        "labels": labels,
        "baseline_distribution": [round(x, 4) for x in p],
        "recent_distribution": [round(x, 4) for x in q],
        "baseline_mean_sentiment": round(baseline_mean, 4),
        "recent_mean_sentiment": round(recent_mean, 4),
        "baseline_rows": int(len(baseline_df)),
        "recent_rows": int(len(recent_df)),
        "threshold": round(threshold, 4),
    }

    result = {
        "run_id": run_id,
        "created_at": created_at,
        "model_name": model_name,
        "status": status,
        "metric": "js_divergence",
        "drift_score": round(drift_score, 4),
        "baseline_window": {
            "start": baseline_start.date().isoformat(),
            "end": (baseline_end.date().isoformat()),
        },
        "recent_window": {
            "start": recent_start.date().isoformat(),
            "end": end_dt.date().isoformat(),
        },
        "details": details,
    }

    _persist_run(result)

    if status != "ok":
        _persist_alert(
            "medium",
            "MODEL_DRIFT_DETECTED",
            "Sentiment distribution drift detected between baseline and recent windows.",
            {"drift_score": round(drift_score, 4), **details},
        )

    return result


def _persist_run(result: Dict[str, Any]) -> None:
    try:
        baseline = result.get("baseline_window") or {}
        recent = result.get("recent_window") or {}
        with session_scope() as session:
            session.merge(
                ModelDriftRun(
                    run_id=str(result.get("run_id")),
                    created_at=str(result.get("created_at")),
                    metric=str(result.get("metric") or "js_divergence"),
                    drift_score=float(result.get("drift_score") or 0.0),
                    baseline_start=str(baseline.get("start") or ""),
                    baseline_end=str(baseline.get("end") or ""),
                    recent_start=str(recent.get("start") or ""),
                    recent_end=str(recent.get("end") or ""),
                    details=json.dumps(result.get("details") or {}, ensure_ascii=True, separators=(",", ":"), default=str),
                )
            )
    except Exception:
        return


def list_drift_runs(limit: int = 20) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 20), 100))
    with session_scope() as session:
        rows = (
            session.execute(
                select(ModelDriftRun).order_by(desc(ModelDriftRun.created_at)).limit(safe_limit)
            )
            .scalars()
            .all()
        )
    result: List[Dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "run_id": row.run_id,
                "created_at": row.created_at,
                "metric": row.metric,
                "drift_score": float(row.drift_score or 0.0),
                "baseline_window": {"start": row.baseline_start, "end": row.baseline_end},
                "recent_window": {"start": row.recent_start, "end": row.recent_end},
                "details": row.details,
            }
        )
    return result
