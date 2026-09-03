from __future__ import annotations

import csv
import uuid
from typing import Any, Dict

import pandas as pd
from sqlalchemy import desc, select

from src.core.database import ModelEvaluation, PROJECT_ROOT, now_utc_iso, session_scope
from src.data_processing.review_store import PROCESSED_DATA_PATH


EVAL_HISTORY_PATH = PROJECT_ROOT / "data" / "processed" / "model_evaluation_history.csv"


def _ensure_eval_history_file() -> None:
    EVAL_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if EVAL_HISTORY_PATH.exists():
        return
    with EVAL_HISTORY_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "run_id",
                "created_at",
                "model_name",
                "coverage",
                "avg_confidence",
                "positive_ratio",
                "negative_ratio",
                "neutral_ratio",
            ]
        )


def _empty_result(model_name: str) -> Dict[str, Any]:
    return {
        "run_id": f"eval-{uuid.uuid4().hex[:12]}",
        "created_at": now_utc_iso(),
        "model_name": model_name,
        "coverage": 0.0,
        "avg_confidence": 0.0,
        "positive_ratio": 0.0,
        "negative_ratio": 0.0,
        "neutral_ratio": 0.0,
    }


def evaluate_model_quality(model_name: str = "nlp_baseline") -> Dict[str, Any]:
    _ensure_eval_history_file()
    if not PROCESSED_DATA_PATH.exists():
        result = _empty_result(model_name=model_name)
    else:
        df = pd.read_csv(PROCESSED_DATA_PATH)
        if df.empty:
            result = _empty_result(model_name=model_name)
        else:
            pos = float((df["sentiment_label"] == "positive").mean())
            neg = float((df["sentiment_label"] == "negative").mean())
            neu = float((df["sentiment_label"] == "neutral").mean())
            confidence = (
                1.0 - (df["sentiment_score"].abs().sub(1.0).abs().mean() / 1.0)
                if "sentiment_score" in df.columns
                else 0.0
            )
            result = {
                "run_id": f"eval-{uuid.uuid4().hex[:12]}",
                "created_at": now_utc_iso(),
                "model_name": model_name,
                "coverage": round(min(1.0, len(df) / 200.0), 3),
                "avg_confidence": round(max(0.0, min(1.0, confidence)), 3),
                "positive_ratio": round(pos, 3),
                "negative_ratio": round(neg, 3),
                "neutral_ratio": round(neu, 3),
            }

    with EVAL_HISTORY_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                result["run_id"],
                result["created_at"],
                result["model_name"],
                result["coverage"],
                result["avg_confidence"],
                result["positive_ratio"],
                result["negative_ratio"],
                result["neutral_ratio"],
            ]
        )

    with session_scope() as session:
        session.merge(
            ModelEvaluation(
                run_id=str(result["run_id"]),
                created_at=str(result["created_at"]),
                model_name=str(result["model_name"]),
                coverage=float(result["coverage"]),
                avg_confidence=float(result["avg_confidence"]),
                positive_ratio=float(result["positive_ratio"]),
                negative_ratio=float(result["negative_ratio"]),
                neutral_ratio=float(result["neutral_ratio"]),
            )
        )

    return result


def get_latest_evaluation() -> Dict[str, Any] | None:
    with session_scope() as session:
        row = session.execute(
            select(ModelEvaluation).order_by(desc(ModelEvaluation.created_at)).limit(1)
        ).scalar_one_or_none()
    if not row:
        return None
    return {
        "run_id": row.run_id,
        "created_at": row.created_at,
        "model_name": row.model_name,
        "coverage": row.coverage,
        "avg_confidence": row.avg_confidence,
        "positive_ratio": row.positive_ratio,
        "negative_ratio": row.negative_ratio,
        "neutral_ratio": row.neutral_ratio,
    }
