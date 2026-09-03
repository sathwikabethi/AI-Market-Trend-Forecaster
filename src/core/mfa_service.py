from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import HTTPException
from sqlalchemy import select

from src.core.database import UserMFA, now_utc_iso, session_scope
from src.core.mfa import (
    dump_backup_hashes,
    generate_backup_codes,
    generate_base32_secret,
    hash_backup_code,
    load_backup_hashes,
    verify_totp,
)


def begin_mfa_setup(user_id: int, issuer: str, account_name: str) -> Dict[str, Any]:
    uid = int(user_id)
    if uid <= 0:
        raise HTTPException(status_code=400, detail="Invalid user.")

    secret = generate_base32_secret()
    backup_codes = generate_backup_codes(count=8)
    backup_hashes = dump_backup_hashes(backup_codes)
    otpauth_url = f"otpauth://totp/{issuer}:{account_name}?secret={secret}&issuer={issuer}&digits=6&period=30"

    with session_scope() as session:
        existing = session.execute(select(UserMFA).where(UserMFA.user_id == uid)).scalar_one_or_none()
        if existing and existing.enabled_at:
            raise HTTPException(status_code=409, detail="MFA is already enabled.")
        if existing:
            existing.secret_base32 = secret
            existing.created_at = now_utc_iso()
            existing.enabled_at = None
            existing.backup_codes_hashes = backup_hashes
        else:
            session.add(
                UserMFA(
                    user_id=uid,
                    secret_base32=secret,
                    created_at=now_utc_iso(),
                    enabled_at=None,
                    backup_codes_hashes=backup_hashes,
                )
            )

    return {"secret_base32": secret, "otpauth_url": otpauth_url, "backup_codes": backup_codes}


def enable_mfa(user_id: int, code: str) -> Dict[str, Any]:
    uid = int(user_id)
    if uid <= 0:
        raise HTTPException(status_code=400, detail="Invalid user.")

    with session_scope() as session:
        row = session.execute(select(UserMFA).where(UserMFA.user_id == uid)).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="MFA setup not found.")
        if row.enabled_at:
            return {"status": "already_enabled"}
        if not verify_totp(row.secret_base32, code, window_steps=1):
            raise HTTPException(status_code=401, detail="Invalid MFA code.")
        row.enabled_at = now_utc_iso()
        return {"status": "enabled", "enabled_at": row.enabled_at}


def disable_mfa(user_id: int) -> Dict[str, Any]:
    uid = int(user_id)
    if uid <= 0:
        raise HTTPException(status_code=400, detail="Invalid user.")
    with session_scope() as session:
        row = session.execute(select(UserMFA).where(UserMFA.user_id == uid)).scalar_one_or_none()
        if not row:
            return {"status": "not_enabled"}
        session.delete(row)
    return {"status": "disabled"}


def is_mfa_enabled(user_id: int) -> bool:
    uid = int(user_id)
    if uid <= 0:
        return False
    with session_scope() as session:
        row = session.execute(select(UserMFA).where(UserMFA.user_id == uid)).scalar_one_or_none()
    return bool(row and row.enabled_at)


def verify_mfa_code(user_id: int, code: str) -> bool:
    uid = int(user_id)
    if uid <= 0:
        return False
    candidate = (code or "").strip().upper()
    if not candidate:
        return False

    with session_scope() as session:
        row = session.execute(select(UserMFA).where(UserMFA.user_id == uid)).scalar_one_or_none()
        if not row or not row.enabled_at:
            return False

        if verify_totp(row.secret_base32, candidate, window_steps=1):
            return True

        # Backup code path: consume on use.
        hashes = load_backup_hashes(row.backup_codes_hashes)
        candidate_hash = hash_backup_code(candidate)
        if candidate_hash not in hashes:
            return False
        hashes = [h for h in hashes if h != candidate_hash]
        row.backup_codes_hashes = json.dumps(hashes, ensure_ascii=True, separators=(",", ":"))
        return True
