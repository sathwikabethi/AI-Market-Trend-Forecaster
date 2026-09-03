from __future__ import annotations

import json
from typing import Any, Dict, List

from sqlalchemy import desc, select

from src.core.database import Alert, now_utc_iso, session_scope


def _persist_alert(level: str, code: str, message: str, payload: Dict[str, Any]) -> None:
    with session_scope() as session:
        session.add(
            Alert(
                created_at=now_utc_iso(),
                level=level,
                code=code,
                message=message,
                payload=json.dumps(payload),
            )
        )


def evaluate_kpi_alerts(kpis: Dict[str, float]) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    risk = float(kpis.get("risk_index", 0.0) or 0.0)
    customer = float(kpis.get("customer_satisfaction_index", 0.0) or 0.0)
    uncertainty = float(kpis.get("uncertainty_index", 0.0) or 0.0)

    if risk >= 0.7:
        alerts.append(
            {
                "level": "high",
                "code": "KPI_HIGH_RISK",
                "message": "Risk index crossed high threshold.",
                "payload": {"risk_index": round(risk, 3)},
            }
        )
    if customer <= 0.3:
        alerts.append(
            {
                "level": "medium",
                "code": "KPI_LOW_SATISFACTION",
                "message": "Customer satisfaction is below target.",
                "payload": {"customer_satisfaction_index": round(customer, 3)},
            }
        )
    if uncertainty >= 0.6:
        alerts.append(
            {
                "level": "medium",
                "code": "KPI_HIGH_UNCERTAINTY",
                "message": "Model uncertainty is elevated.",
                "payload": {"uncertainty_index": round(uncertainty, 3)},
            }
        )

    for alert in alerts:
        _persist_alert(
            alert["level"],
            alert["code"],
            alert["message"],
            alert["payload"],
        )
    return alerts


def list_alerts(limit: int = 50) -> List[Dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            select(Alert).order_by(desc(Alert.id)).limit(max(1, int(limit)))
        ).scalars().all()
    return [
        {
            "id": int(row.id),
            "created_at": row.created_at,
            "level": row.level,
            "code": row.code,
            "message": row.message,
            "payload": row.payload,
        }
        for row in rows
    ]
