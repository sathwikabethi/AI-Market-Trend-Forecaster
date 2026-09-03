from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session as OrmSession

from src.core.auth import hash_password, revoke_all_sessions_for_user
from src.core.database import OneTimeToken, User, now_utc_iso
from src.core.database import session_scope
from src.core.settings import settings


TOKEN_TYPE_EMAIL_VERIFY = "email_verify"
TOKEN_TYPE_PASSWORD_RESET = "password_reset"

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _sha256_hex(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _normalize_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if not EMAIL_PATTERN.match(normalized):
        raise HTTPException(status_code=400, detail="Invalid email format.")
    return normalized


def _parse_iso(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value))
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _issue_token_for_user(
    session: OrmSession,
    *,
    user_id: int,
    token_type: str,
    ttl_minutes: int,
    details: Dict[str, Any] | None = None,
) -> Dict[str, str]:
    uid = int(user_id)
    if uid <= 0:
        raise HTTPException(status_code=400, detail="Invalid user.")
    ttype = (token_type or "").strip()
    if not ttype:
        raise HTTPException(status_code=400, detail="Invalid token type.")

    now = datetime.now(timezone.utc)
    now_iso = now_utc_iso()
    expires_at_dt = now + timedelta(minutes=max(1, int(ttl_minutes)))
    expires_at_iso = expires_at_dt.isoformat(timespec="seconds")

    raw = secrets.token_urlsafe(32)
    token_hash = _sha256_hex(raw)
    token_id = f"ott-{uuid.uuid4().hex}"

    # Keep the newest token as the only valid token for this (user, type) pair.
    session.execute(
        update(OneTimeToken)
        .where(
            OneTimeToken.user_id == uid,
            OneTimeToken.token_type == ttype,
            OneTimeToken.used_at.is_(None),
        )
        .values(used_at=now_iso)
    )

    payload = json.dumps(details or {}, ensure_ascii=True, separators=(",", ":"), default=str) if details else None
    session.add(
        OneTimeToken(
            token_id=token_id,
            user_id=uid,
            token_type=ttype,
            token_hash=token_hash,
            created_at=now_iso,
            expires_at=expires_at_iso,
            used_at=None,
            details=payload,
        )
    )

    return {"token": raw, "token_id": token_id, "expires_at": expires_at_iso}


def _consume_token(
    session: OrmSession,
    *,
    token_value: str,
    token_type: str,
) -> Tuple[OneTimeToken, User]:
    raw = (token_value or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Token required.")
    token_hash = _sha256_hex(raw)

    row = session.execute(
        select(OneTimeToken).where(
            OneTimeToken.token_hash == token_hash,
            OneTimeToken.token_type == token_type,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid token.")
    if row.used_at:
        raise HTTPException(status_code=409, detail="Token already used.")

    now = datetime.now(timezone.utc)
    expires_at = _parse_iso(row.expires_at)
    if now > expires_at:
        row.used_at = now_utc_iso()
        raise HTTPException(status_code=401, detail="Token has expired.")

    user = session.execute(select(User).where(User.id == int(row.user_id))).scalar_one_or_none()
    if not user:
        row.used_at = now_utc_iso()
        raise HTTPException(status_code=401, detail="Token is invalid.")

    return row, user


def request_email_verification(
    *,
    email: str,
    ttl_minutes: int = 60,
) -> Dict[str, Any]:
    normalized = _normalize_email(email)
    with session_scope() as session:
        user = session.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
        if not user:
            # Do not reveal whether a user exists.
            return {"status": "sent"}
        if user.email_verified_at:
            return {"status": "already_verified"}

        meta = _issue_token_for_user(
            session,
            user_id=int(user.id),
            token_type=TOKEN_TYPE_EMAIL_VERIFY,
            ttl_minutes=ttl_minutes,
            details={"email": normalized},
        )
        # In production, the token should be delivered over email, not returned by the API.
        if settings.app_env.strip().lower() == "production":
            meta.pop("token", None)
        return {"status": "sent", **meta}


def confirm_email_verification(*, token: str) -> Dict[str, Any]:
    with session_scope() as session:
        token_row, user = _consume_token(session, token_value=token, token_type=TOKEN_TYPE_EMAIL_VERIFY)
        now_iso = now_utc_iso()
        if not user.email_verified_at:
            user.email_verified_at = now_iso
            status = "verified"
        else:
            status = "already_verified"
        token_row.used_at = now_iso
        return {"status": status, "email_verified_at": user.email_verified_at}


def request_password_reset(
    *,
    email: str,
    ttl_minutes: int = 30,
) -> Dict[str, Any]:
    normalized = _normalize_email(email)
    with session_scope() as session:
        user = session.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
        if not user:
            # Do not reveal whether a user exists.
            return {"status": "sent"}

        meta = _issue_token_for_user(
            session,
            user_id=int(user.id),
            token_type=TOKEN_TYPE_PASSWORD_RESET,
            ttl_minutes=ttl_minutes,
            details={"email": normalized},
        )
        if settings.app_env.strip().lower() == "production":
            meta.pop("token", None)
        return {"status": "sent", **meta}


def confirm_password_reset(*, token: str, new_password: str) -> Dict[str, Any]:
    with session_scope() as session:
        token_row, user = _consume_token(session, token_value=token, token_type=TOKEN_TYPE_PASSWORD_RESET)
        now_iso = now_utc_iso()

        # Reset password and revoke all active sessions/refresh tokens.
        user.password_hash = hash_password(new_password)
        token_row.used_at = now_iso
        session.execute(
            update(OneTimeToken)
            .where(
                OneTimeToken.user_id == int(user.id),
                OneTimeToken.token_type == TOKEN_TYPE_PASSWORD_RESET,
                OneTimeToken.used_at.is_(None),
            )
            .values(used_at=now_iso)
        )
        revoke_all_sessions_for_user(int(user.id), session=session)
        return {"status": "reset"}

