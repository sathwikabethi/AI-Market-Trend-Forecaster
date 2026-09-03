from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd

from src.core.database import DataQualityRun, now_utc_iso, session_scope
from src.data_processing.review_store import PROCESSED_DATA_PATH, initialize_datasets


REQUIRED_COLUMNS = {
    "review_id",
    "date",
    "product",
    "product_name",
    "source",
    "rating",
    "review_text",
    "cleaned_text",
    "sentiment_label",
    "sentiment_score",
}


def _check(name: str, status: str, *, value: Any = None, message: str | None = None) -> Dict[str, Any]:
    return {"name": name, "status": status, "value": value, "message": message}


def _score(checks: List[Dict[str, Any]]) -> float:
    penalty = 0.0
    for item in checks:
        status = str(item.get("status", "")).lower()
        if status == "fail":
            penalty += 0.25
        elif status == "warn":
            penalty += 0.1
    return float(max(0.0, min(1.0, 1.0 - penalty)))


def run_data_quality_checks(note: str | None = None) -> Dict[str, Any]:
    initialize_datasets()
    run_id = f"dq-{uuid.uuid4().hex[:12]}"
    created_at = now_utc_iso()

    checks: List[Dict[str, Any]] = []
    details: Dict[str, Any] = {"processed_path": str(PROCESSED_DATA_PATH), "note": note}

    if not PROCESSED_DATA_PATH.exists():
        checks.append(_check("processed_exists", "fail", message="Processed dataset missing."))
        score = _score(checks)
        status = "fail"
        _store_dq_run(run_id, created_at, status, score, checks, details)
        return _run_payload(run_id, created_at, status, score, checks, details)

    try:
        df = pd.read_csv(PROCESSED_DATA_PATH)
    except Exception as exc:
        checks.append(_check("processed_readable", "fail", message=str(exc)))
        score = _score(checks)
        status = "fail"
        _store_dq_run(run_id, created_at, status, score, checks, details)
        return _run_payload(run_id, created_at, status, score, checks, details)

    checks.append(_check("processed_readable", "pass", value=int(len(df))))

    missing_cols = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing_cols:
        checks.append(_check("schema_required_columns", "fail", value=missing_cols))
    else:
        checks.append(_check("schema_required_columns", "pass"))

    if df.empty:
        checks.append(_check("rows_non_empty", "fail", value=0, message="No processed rows."))
    else:
        checks.append(_check("rows_non_empty", "pass", value=int(len(df))))

    # Empty text ratio
    if "cleaned_text" in df.columns:
        empty_clean = int(df["cleaned_text"].fillna("").astype(str).str.strip().eq("").sum())
        ratio = float(empty_clean / max(1, len(df)))
        status = "pass" if ratio <= 0.02 else "warn" if ratio <= 0.08 else "fail"
        checks.append(_check("empty_cleaned_text_ratio", status, value=round(ratio, 4)))

    # Date validity / freshness
    if "date" in df.columns:
        parsed = pd.to_datetime(df["date"], errors="coerce", utc=True)
        invalid = int(parsed.isna().sum())
        invalid_ratio = float(invalid / max(1, len(df)))
        checks.append(
            _check(
                "date_parseable_ratio",
                "pass" if invalid_ratio <= 0.01 else "warn" if invalid_ratio <= 0.05 else "fail",
                value=round(1.0 - invalid_ratio, 4),
            )
        )
        max_dt = parsed.max()
        if pd.isna(max_dt):
            checks.append(_check("data_freshness_days", "fail", message="No valid dates."))
        else:
            days = int((datetime.now(timezone.utc) - max_dt.to_pydatetime()).days)
            checks.append(
                _check(
                    "data_freshness_days",
                    "pass" if days <= 45 else "warn" if days <= 120 else "fail",
                    value=days,
                )
            )

    # Rating range
    if "rating" in df.columns:
        rating = pd.to_numeric(df["rating"], errors="coerce")
        invalid = int(((rating < 1) | (rating > 5) | rating.isna()).sum())
        invalid_ratio = float(invalid / max(1, len(df)))
        checks.append(
            _check(
                "rating_valid_ratio",
                "pass" if invalid_ratio <= 0.01 else "warn" if invalid_ratio <= 0.05 else "fail",
                value=round(1.0 - invalid_ratio, 4),
            )
        )

    # Sentiment score range
    if "sentiment_score" in df.columns:
        score_series = pd.to_numeric(df["sentiment_score"], errors="coerce")
        invalid = int(((score_series < -1.0) | (score_series > 1.0) | score_series.isna()).sum())
        invalid_ratio = float(invalid / max(1, len(df)))
        checks.append(
            _check(
                "sentiment_score_valid_ratio",
                "pass" if invalid_ratio <= 0.01 else "warn" if invalid_ratio <= 0.05 else "fail",
                value=round(1.0 - invalid_ratio, 4),
            )
        )

    # Sentiment label distribution
    if "sentiment_label" in df.columns and not df.empty:
        counts = df["sentiment_label"].fillna("neutral").astype(str).str.lower().value_counts()
        dominant_ratio = float((counts.max() / max(1, int(len(df))))) if not counts.empty else 0.0
        checks.append(
            _check(
                "sentiment_label_dominant_ratio",
                "pass" if dominant_ratio <= 0.9 else "warn" if dominant_ratio <= 0.97 else "fail",
                value=round(dominant_ratio, 4),
            )
        )
        details["sentiment_label_counts"] = {str(k): int(v) for k, v in counts.to_dict().items()}

    # Duplicate review ids
    if "review_id" in df.columns and not df.empty:
        dupes = int(df["review_id"].astype(str).duplicated().sum())
        dupe_ratio = float(dupes / max(1, len(df)))
        checks.append(
            _check(
                "duplicate_review_id_ratio",
                "pass" if dupe_ratio == 0.0 else "warn" if dupe_ratio <= 0.01 else "fail",
                value=round(dupe_ratio, 4),
            )
        )

    overall_status = "ok"
    for item in checks:
        if str(item.get("status", "")).lower() == "fail":
            overall_status = "fail"
            break
    dq_score = _score(checks)

    _store_dq_run(run_id, created_at, overall_status, dq_score, checks, details)
    return _run_payload(run_id, created_at, overall_status, dq_score, checks, details)


def _run_payload(
    run_id: str,
    created_at: str,
    status: str,
    score: float,
    checks: List[Dict[str, Any]],
    details: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "created_at": created_at,
        "status": status,
        "score": round(float(score), 4),
        "checks": checks,
        "details": details,
    }


def _store_dq_run(
    run_id: str,
    created_at: str,
    status: str,
    score: float,
    checks: List[Dict[str, Any]],
    details: Dict[str, Any],
) -> None:
    try:
        with session_scope() as session:
            session.add(
                DataQualityRun(
                    run_id=run_id,
                    created_at=created_at,
                    status=str(status),
                    score=float(score),
                    checks=json.dumps(checks, ensure_ascii=True, separators=(",", ":"), default=str),
                    details=json.dumps(details, ensure_ascii=True, separators=(",", ":"), default=str),
                )
            )
    except Exception:
        return


def list_data_quality_runs(limit: int = 20) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 20), 100))
    with session_scope() as session:
        rows = (
            session.query(DataQualityRun)
            .order_by(DataQualityRun.created_at.desc())
            .limit(safe_limit)
            .all()
        )
    result: List[Dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "run_id": row.run_id,
                "created_at": row.created_at,
                "status": row.status,
                "score": float(row.score or 0.0),
                "checks": row.checks,
                "details": row.details,
            }
        )
    return result
