from src.analytics.business_metrics import compute_business_kpis


def test_compute_business_kpis_empty_payload():
    result = compute_business_kpis({})
    assert result["customer_satisfaction_index"] == 0.0
    assert result["risk_index"] == 0.0
    assert result["confidence_index"] == 0.0
    assert result["uncertainty_index"] == 1.0


def test_compute_business_kpis_positive_dominant():
    payload = {
        "texture": {
            "label": "POSITIVE",
            "confidence": 0.82,
            "scores": {"positive": 0.82, "negative": 0.05, "neutral": 0.13},
        },
        "price": {
            "label": "NEGATIVE",
            "confidence": 0.35,
            "scores": {"positive": 0.15, "negative": 0.35, "neutral": 0.5},
        },
    }
    result = compute_business_kpis(payload)
    assert 0.0 <= result["customer_satisfaction_index"] <= 1.0
    assert 0.0 <= result["risk_index"] <= 1.0
    assert result["customer_satisfaction_index"] > result["risk_index"]
    assert 0.0 <= result["net_sentiment_index"] <= 1.0
