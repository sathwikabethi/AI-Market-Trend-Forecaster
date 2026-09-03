from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = PROJECT_ROOT / "data" / "processed" / "model_evaluation_history.csv"
OUT_PATH = PROJECT_ROOT / "models" / "model_evaluation.txt"


@dataclass(frozen=True)
class EvalRow:
    run_id: str
    created_at: str
    model_name: str
    coverage: float
    avg_confidence: float
    positive_ratio: float
    negative_ratio: float
    neutral_ratio: float


def _safe_float(value: str) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def read_history(path: Path) -> list[EvalRow]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    result: list[EvalRow] = []
    for row in rows:
        result.append(
            EvalRow(
                run_id=str(row.get("run_id", "")).strip(),
                created_at=str(row.get("created_at", "")).strip(),
                model_name=str(row.get("model_name", "")).strip(),
                coverage=_safe_float(str(row.get("coverage", "0"))),
                avg_confidence=_safe_float(str(row.get("avg_confidence", "0"))),
                positive_ratio=_safe_float(str(row.get("positive_ratio", "0"))),
                negative_ratio=_safe_float(str(row.get("negative_ratio", "0"))),
                neutral_ratio=_safe_float(str(row.get("neutral_ratio", "0"))),
            )
        )
    return result


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def render(rows: list[EvalRow]) -> str:
    latest = rows[-1] if rows else None
    tail = rows[-10:] if rows else []

    def fmt(x: float, digits: int = 3) -> str:
        return f"{x:.{digits}f}"

    lines: list[str] = []
    lines.append("Model Evaluation (Operational Metrics)")
    lines.append("====================================")
    lines.append("")
    lines.append(
        "This project records lightweight, operational evaluation metrics for the NLP"
    )
    lines.append(
        "pipeline based on the current processed dataset. These are meant to answer:"
    )
    lines.append('"Is the model producing outputs and what is the label distribution?"')
    lines.append("")
    lines.append(
        "This is NOT a supervised accuracy/precision/recall evaluation because the"
    )
    lines.append(
        "dataset in this repo does not include ground-truth sentiment labels."
    )
    lines.append("")
    lines.append("Source Of Truth")
    lines.append("---------------")
    lines.append("- CSV history: data/processed/model_evaluation_history.csv")
    lines.append("- Database table: model_evaluations (SQLite by default in data/app.db)")
    lines.append("- API surface: GET /admin/overview (includes latest_evaluation)")
    lines.append("")

    if latest is None:
        lines.append("Latest Recorded Run")
        lines.append("-------------------")
        lines.append("No evaluation history found yet.")
    else:
        lines.append("Latest Recorded Run")
        lines.append("-------------------")
        lines.append(f"- run_id: {latest.run_id}")
        lines.append(f"- created_at (UTC): {latest.created_at}")
        lines.append(f"- model_name: {latest.model_name}")
        lines.append(f"- coverage: {fmt(latest.coverage, 3)}")
        lines.append(f"- avg_confidence: {fmt(latest.avg_confidence, 3)}")
        lines.append(f"- positive_ratio: {fmt(latest.positive_ratio, 3)}")
        lines.append(f"- negative_ratio: {fmt(latest.negative_ratio, 3)}")
        lines.append(f"- neutral_ratio: {fmt(latest.neutral_ratio, 3)}")

    if tail:
        lines.append("")
        lines.append("Recent Average (Last 10 Runs)")
        lines.append("-----------------------------")
        lines.append(f"- runs: {len(tail)}")
        lines.append(f"- coverage: {fmt(mean([r.coverage for r in tail]), 3)}")
        lines.append(f"- avg_confidence: {fmt(mean([r.avg_confidence for r in tail]), 3)}")
        lines.append(f"- positive_ratio: {fmt(mean([r.positive_ratio for r in tail]), 3)}")
        lines.append(f"- negative_ratio: {fmt(mean([r.negative_ratio for r in tail]), 3)}")
        lines.append(f"- neutral_ratio: {fmt(mean([r.neutral_ratio for r in tail]), 3)}")

    lines.append("")
    lines.append("How To Refresh")
    lines.append("--------------")
    lines.append(
        "The backend writes new evaluation rows on startup (lifespan hook) by calling"
    )
    lines.append("evaluate_model_quality(). You can also trigger it manually with:")
    lines.append("")
    lines.append(
        'python -c "from src.core.evaluation import evaluate_model_quality; print(evaluate_model_quality())"'
    )
    lines.append("")
    lines.append("This file can be regenerated anytime with:")
    lines.append("")
    lines.append("python scripts/update_model_docs.py")
    lines.append("")
    lines.append("Interpretation")
    lines.append("--------------")
    lines.append("- coverage: Proxy based on processed row count (capped at 1.0).")
    lines.append(
        "- avg_confidence: Derived from sentiment_score distribution in processed data."
    )
    lines.append("- *_ratio: Ratio of labels in processed data.")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    rows = read_history(HISTORY_PATH)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(render(rows), encoding="utf-8")
    print(f"Wrote: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

