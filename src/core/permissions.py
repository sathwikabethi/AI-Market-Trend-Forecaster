from __future__ import annotations

from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy import delete, select

from src.core.database import User, UserPermission, now_utc_iso, session_scope


def _normalize_permission(permission: str) -> str:
    value = (permission or "").strip().lower()
    if not value or len(value) < 3 or len(value) > 160:
        raise HTTPException(status_code=400, detail="Invalid permission string.")
    return value


def grant_user_permission(email: str, permission: str) -> Dict[str, Any]:
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="Email required.")
    perm = _normalize_permission(permission)

    with session_scope() as session:
        user = session.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        existing = session.execute(
            select(UserPermission).where(
                UserPermission.user_id == int(user.id),
                UserPermission.permission == perm,
            )
        ).scalar_one_or_none()
        if existing:
            return {"status": "already_granted", "email": normalized_email, "permission": perm}

        session.add(
            UserPermission(
                user_id=int(user.id),
                permission=perm,
                created_at=now_utc_iso(),
            )
        )

    return {"status": "granted", "email": normalized_email, "permission": perm}


def revoke_user_permission(email: str, permission: str) -> Dict[str, Any]:
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="Email required.")
    perm = _normalize_permission(permission)

    with session_scope() as session:
        user = session.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        session.execute(
            delete(UserPermission).where(
                UserPermission.user_id == int(user.id),
                UserPermission.permission == perm,
            )
        )

    return {"status": "revoked", "email": normalized_email, "permission": perm}


def list_user_permissions(email: str) -> List[str]:
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="Email required.")

    with session_scope() as session:
        user = session.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        perms = session.execute(
            select(UserPermission.permission).where(UserPermission.user_id == int(user.id))
        ).scalars().all()

    return [str(item) for item in perms if item]
