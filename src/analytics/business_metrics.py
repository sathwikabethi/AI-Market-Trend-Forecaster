from __future__ import annotations

from typing import Any, Dict, cast


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        # `float(...)` accepts many runtime types; for static typing we treat inputs as dynamic.
        return float(cast(Any, value))
    except Exception:
        return default


def compute_business_kpis(aspect_results: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    if not isinstance(aspect_results, dict) or not aspect_results:
        return {
            "customer_satisfaction_index": 0.0,
            "risk_index": 0.0,
            "uncertainty_index": 1.0,
            "confidence_index": 0.0,
            "net_sentiment_index": 0.5,
            "aspect_coverage_index": 0.0,
        }

    pos_signal = []
    neg_signal = []
    confidences = []
    net_scores = []

    for result in aspect_results.values():
        if not isinstance(result, dict):
            continue

        scores = result.get("scores", {})
        if not isinstance(scores, dict):
            scores = {}

        pos = _clamp01(_safe_float(scores.get("positive", 0.0)))
        neg = _clamp01(_safe_float(scores.get("negative", 0.0)))
        neutral = _clamp01(_safe_float(scores.get("neutral", max(0.0, 1.0 - pos - neg))))
        conf = _clamp01(_safe_float(result.get("confidence", 0.0)))
        label = str(result.get("label", "NEUTRAL")).upper()

        if label == "POSITIVE":
            pos_signal.append(max(conf, pos))
            neg_signal.append(neg * 0.6)
        elif label == "NEGATIVE":
            pos_signal.append(pos * 0.6)
            neg_signal.append(max(conf, neg))
        else:
            # Neutral contributes modestly to both sides based on probability mass.
            pos_signal.append(pos * 0.75 + neutral * 0.1)
            neg_signal.append(neg * 0.75 + neutral * 0.1)

        confidences.append(conf)
        net_scores.append(pos - neg)

    n = max(1, len(pos_signal))
    avg_pos = _clamp01(sum(pos_signal) / n)
    avg_neg = _clamp01(sum(neg_signal) / n)
    avg_conf = _clamp01(sum(confidences) / n if confidences else 0.0)
    avg_net = (sum(net_scores) / n) if net_scores else 0.0
    net_index = _clamp01((avg_net + 1.0) / 2.0)

    # Approximate how many aspect buckets are represented (target 5+ for full coverage).
    coverage = _clamp01(len(pos_signal) / 5.0)

    return {
        "customer_satisfaction_index": round(avg_pos, 3),
        "risk_index": round(avg_neg, 3),
        "uncertainty_index": round(_clamp01(1.0 - avg_conf), 3),
        "confidence_index": round(avg_conf, 3),
        "net_sentiment_index": round(net_index, 3),
        "aspect_coverage_index": round(coverage, 3),
    }
