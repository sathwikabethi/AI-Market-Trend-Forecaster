from __future__ import annotations

import json
from typing import Any, Dict, List

from sqlalchemy import desc, select

from src.core.database import SecurityAuditLog, now_utc_iso, session_scope


def log_security_event(
    *,
    event_type: str,
    status: str,
    actor_user_id: int | None = None,
    actor_email: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    details: Dict[str, Any] | str | None = None,
) -> None:
    """Best-effort append-only audit logging. Never raises to callers."""

    try:
        payload: str | None
        if details is None:
            payload = None
        elif isinstance(details, str):
            payload = details
        else:
            payload = json.dumps(details, ensure_ascii=True, separators=(",", ":"), default=str)

        with session_scope() as session:
            session.add(
                SecurityAuditLog(
                    created_at=now_utc_iso(),
                    event_type=str(event_type or "")[:80] or "unknown",
                    status=str(status or "")[:30] or "unknown",
                    actor_user_id=int(actor_user_id) if actor_user_id is not None else None,
                    actor_email=(str(actor_email or "").strip().lower() or None),
                    ip_address=(str(ip_address or "")[:80] or None),
                    user_agent=(str(user_agent or "")[:1000] or None),
                    details=payload,
                )
            )
    except Exception:
        # Audit logs should not impact business flows.
        return


def list_security_audit_logs(limit: int = 50) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 50), 200))
    with session_scope() as session:
        rows = (
            session.execute(
                select(SecurityAuditLog)
                .order_by(desc(SecurityAuditLog.created_at))
                .limit(safe_limit)
            )
            .scalars()
            .all()
        )
    return [
        {
            "id": int(row.id),
            "created_at": row.created_at,
            "event_type": row.event_type,
            "status": row.status,
            "actor_user_id": row.actor_user_id,
            "actor_email": row.actor_email,
            "ip_address": row.ip_address,
            "user_agent": row.user_agent,
            "details": row.details,
        }
        for row in rows
    ]
