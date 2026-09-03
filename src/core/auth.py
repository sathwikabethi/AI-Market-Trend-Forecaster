from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, TypedDict

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from src.core.database import ApiKey, AuthSession, RefreshToken, User, UserPermission, now_utc_iso, session_scope
from src.core.settings import settings


JWT_SECRET = os.environ.get("JWT_SECRET", "change-this-dev-secret")
JWT_ISSUER = os.environ.get("JWT_ISSUER", "caresense-ai")
TOKEN_TTL_MINUTES = int(os.environ.get("TOKEN_TTL_MINUTES", "120"))
REFRESH_TOKEN_TTL_DAYS = int(os.environ.get("REFRESH_TOKEN_TTL_DAYS", "30"))
ACCESS_COOKIE_NAME = os.environ.get("AUTH_ACCESS_COOKIE_NAME", "tf_access_token").strip() or "tf_access_token"
REFRESH_COOKIE_NAME = os.environ.get("AUTH_REFRESH_COOKIE_NAME", "tf_refresh_token").strip() or "tf_refresh_token"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@caresense.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")
ADMIN_NAME = os.environ.get("ADMIN_NAME", "Platform Admin")

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_bearer = HTTPBearer(auto_error=False)

_AUTH_LOCK = threading.RLock()
_FAILED_ATTEMPTS: dict[str, list[float]] = {}
_LOCKED_UNTIL: dict[str, float] = {}

try:
    import redis
except Exception:
    redis = None

_REDIS_CLIENT = None
_REDIS_LOCK = threading.RLock()


class AuthUser(TypedDict):
    id: int
    email: str
    name: str
    role: str


class AuthResult(TypedDict):
    access_token: str
    refresh_token: str
    token_type: str
    expires_at: str
    user: AuthUser


def create_api_key(user_id: int, name: str | None = None) -> Dict[str, Any]:
    uid = int(user_id)
    if uid <= 0:
        raise HTTPException(status_code=400, detail="Invalid user id.")

    safe_name = (name or "").strip() or "API Key"
    safe_name = safe_name[:120]

    key_id = f"ak-{uuid.uuid4().hex}"
    secret = secrets.token_urlsafe(32)
    api_key = f"tfak_{key_id}.{secret}"
    token_hash = _sha256_hex(api_key)
    prefix = secret[:8]
    created_at = now_utc_iso()

    with session_scope() as session:
        session.add(
            ApiKey(
                key_id=key_id,
                user_id=uid,
                name=safe_name,
                key_prefix=prefix,
                key_hash=token_hash,
                created_at=created_at,
                last_used_at=None,
                revoked_at=None,
            )
        )

    return {
        "api_key": api_key,
        "key_id": key_id,
        "name": safe_name,
        "prefix": prefix,
        "created_at": created_at,
    }


def list_api_keys(user_id: int) -> list[dict[str, Any]]:
    uid = int(user_id)
    if uid <= 0:
        return []
    with session_scope() as session:
        rows = (
            session.execute(
                select(ApiKey).where(ApiKey.user_id == uid).order_by(ApiKey.created_at.desc())
            )
            .scalars()
            .all()
        )
    return [
        {
            "key_id": str(row.key_id),
            "name": str(row.name),
            "prefix": str(row.key_prefix),
            "created_at": str(row.created_at),
            "last_used_at": str(row.last_used_at) if row.last_used_at else None,
            "revoked_at": str(row.revoked_at) if row.revoked_at else None,
        }
        for row in rows
    ]


def revoke_api_key(user_id: int, key_id: str) -> dict[str, str]:
    uid = int(user_id)
    kid = str(key_id or "").strip()
    if uid <= 0 or not kid:
        raise HTTPException(status_code=400, detail="Invalid request.")

    now_iso = now_utc_iso()
    with session_scope() as session:
        row = session.execute(
            select(ApiKey).where(ApiKey.user_id == uid, ApiKey.key_id == kid)
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="API key not found.")
        row.revoked_at = now_iso
    return {"status": "revoked", "key_id": kid}


def authenticate_api_key(api_key: str) -> AuthUser:
    token_value = (api_key or "").strip()
    if len(token_value) < 20:
        raise HTTPException(status_code=401, detail="Invalid API key.")
    token_hash = _sha256_hex(token_value)
    now_iso = now_utc_iso()

    with session_scope() as session:
        key_row = session.execute(
            select(ApiKey).where(ApiKey.key_hash == token_hash, ApiKey.revoked_at.is_(None))
        ).scalar_one_or_none()
        if not key_row:
            raise HTTPException(status_code=401, detail="Invalid API key.")

        key_row.last_used_at = now_iso

        user_row = session.execute(
            select(User).where(User.id == key_row.user_id)
        ).scalar_one_or_none()
        if not user_row:
            raise HTTPException(status_code=401, detail="User not found.")

        return {
            "id": int(user_row.id),
            "email": str(user_row.email),
            "name": str(user_row.name),
            "role": str(user_row.role),
        }


def _redis_client():
    global _REDIS_CLIENT
    if not settings.redis_url or redis is None:
        return None
    with _REDIS_LOCK:
        if _REDIS_CLIENT is not None:
            return _REDIS_CLIENT
        try:
            _REDIS_CLIENT = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        except Exception:
            _REDIS_CLIENT = None
        return _REDIS_CLIENT


def _lockout_key(email: str) -> str:
    return f"auth:lockout:{email}"


def _failed_key(email: str) -> str:
    return f"auth:failed:{email}"


def _sha256_hex(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _password_hash(password: str, salt_hex: str | None = None) -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    rounds = 260000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, rounds_raw, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        rounds = int(rounds_raw)
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            rounds,
        ).hex()
        return hmac.compare_digest(candidate, digest_hex)
    except Exception:
        return False


def _jwt_encode(payload: Dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    signature = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    encoded_signature = _b64url_encode(signature)
    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


def _jwt_decode(token: str) -> Dict[str, Any]:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid token format.") from exc

    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    expected_signature = hmac.new(
        JWT_SECRET.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(_b64url_encode(expected_signature), encoded_signature):
        raise HTTPException(status_code=401, detail="Invalid token signature.")

    payload_raw = _b64url_decode(encoded_payload).decode("utf-8")
    payload = json.loads(payload_raw)
    exp_ts = int(payload.get("exp", 0) or 0)
    if exp_ts and datetime.now(timezone.utc).timestamp() > exp_ts:
        raise HTTPException(status_code=401, detail="Token has expired.")
    return payload


def _validate_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if not EMAIL_PATTERN.match(normalized):
        raise HTTPException(status_code=400, detail="Invalid email format.")
    return normalized


def _validate_password_strength(password: str) -> None:
    value = password or ""
    if len(value) < 10:
        raise HTTPException(status_code=400, detail="Password must be at least 10 characters.")
    if settings.auth_require_password_upper and not re.search(r"[A-Z]", value):
        raise HTTPException(status_code=400, detail="Password must include at least one uppercase letter.")
    if settings.auth_require_password_lower and not re.search(r"[a-z]", value):
        raise HTTPException(status_code=400, detail="Password must include at least one lowercase letter.")
    if settings.auth_require_password_digit and not re.search(r"[0-9]", value):
        raise HTTPException(status_code=400, detail="Password must include at least one digit.")


def validate_password_strength(password: str) -> None:
    _validate_password_strength(password)


def hash_password(password: str) -> str:
    _validate_password_strength(password)
    return _password_hash(password)


def verify_user_password(user_id: int, password: str) -> bool:
    uid = int(user_id)
    if uid <= 0:
        return False
    with session_scope() as session:
        row = session.execute(select(User).where(User.id == uid)).scalar_one_or_none()
    if not row:
        return False
    return _verify_password(password, row.password_hash)


def _prune_old_attempts(email: str, now_ts: float) -> None:
    attempts = _FAILED_ATTEMPTS.get(email, [])
    window = max(30, int(settings.auth_lockout_seconds))
    _FAILED_ATTEMPTS[email] = [item for item in attempts if now_ts - item <= window]


def _record_failed_attempt(email: str) -> None:
    client = _redis_client()
    if client is not None:
        try:
            window = max(30, int(settings.auth_lockout_seconds))
            fails_key = _failed_key(email)
            count = int(client.incr(fails_key))
            client.expire(fails_key, window)
            if count >= max(1, int(settings.auth_max_failed_attempts)):
                client.setex(_lockout_key(email), max(30, int(settings.auth_lockout_seconds)), "1")
            return
        except Exception:
            # Fall back to in-memory if Redis is unhealthy.
            pass

    now_ts = time.time()
    with _AUTH_LOCK:
        _prune_old_attempts(email, now_ts)
        attempts = _FAILED_ATTEMPTS.get(email, [])
        attempts.append(now_ts)
        _FAILED_ATTEMPTS[email] = attempts
        if len(attempts) >= max(1, int(settings.auth_max_failed_attempts)):
            _LOCKED_UNTIL[email] = now_ts + max(30, int(settings.auth_lockout_seconds))


def _ensure_not_locked(email: str) -> None:
    client = _redis_client()
    if client is not None:
        try:
            ttl = int(client.ttl(_lockout_key(email)))
            if ttl and ttl > 0:
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many failed attempts. Try again in {ttl} seconds.",
                )
            return
        except HTTPException:
            raise
        except Exception:
            # Fall back to in-memory if Redis is unhealthy.
            pass

    now_ts = time.time()
    with _AUTH_LOCK:
        locked_until = _LOCKED_UNTIL.get(email)
        if locked_until and now_ts < locked_until:
            remaining = int(locked_until - now_ts)
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed attempts. Try again in {remaining} seconds.",
            )
        if locked_until and now_ts >= locked_until:
            _LOCKED_UNTIL.pop(email, None)
            _FAILED_ATTEMPTS.pop(email, None)


def _clear_failed_attempts(email: str) -> None:
    client = _redis_client()
    if client is not None:
        try:
            client.delete(_failed_key(email), _lockout_key(email))
            return
        except Exception:
            # Fall back to in-memory if Redis is unhealthy.
            pass
    with _AUTH_LOCK:
        _FAILED_ATTEMPTS.pop(email, None)
        _LOCKED_UNTIL.pop(email, None)


def create_user(email: str, name: str, password: str, role: str = "user") -> Dict[str, Any]:
    normalized_email = _validate_email(email)
    safe_name = (name or "").strip()
    if len(safe_name) < 2:
        raise HTTPException(status_code=400, detail="Name must be at least 2 characters.")
    _validate_password_strength(password)

    with session_scope() as session:
        existing = session.execute(
            select(User).where(User.email == normalized_email)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="User already exists.")

        user = User(
            email=normalized_email,
            name=safe_name,
            password_hash=_password_hash(password),
            role=role,
            created_at=now_utc_iso(),
            email_verified_at=None,
        )
        session.add(user)
        session.flush()
        return {
            "id": int(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "created_at": user.created_at,
        }


def create_default_admin_user() -> None:
    with session_scope() as session:
        row = session.execute(
            select(User).where(User.email == ADMIN_EMAIL.lower())
        ).scalar_one_or_none()
        if row:
            return
        session.add(
            User(
                email=ADMIN_EMAIL.lower(),
                name=ADMIN_NAME,
                password_hash=_password_hash(ADMIN_PASSWORD),
                role="admin",
                created_at=now_utc_iso(),
                email_verified_at=now_utc_iso(),
            )
        )


def _create_session(user_id: int, ip_address: str | None, user_agent: str | None) -> Dict[str, str]:
    now = datetime.now(timezone.utc)
    expires_at_dt = now + timedelta(minutes=TOKEN_TTL_MINUTES)
    session_id = f"sess-{uuid.uuid4().hex}"
    jti = uuid.uuid4().hex
    with session_scope() as session:
        session.add(
            AuthSession(
                session_id=session_id,
                user_id=int(user_id),
                jti=jti,
                created_at=now_utc_iso(),
                expires_at=expires_at_dt.isoformat(timespec="seconds"),
                revoked_at=None,
                ip_address=(ip_address or "")[:80] or None,
                user_agent=(user_agent or "")[:1000] or None,
            )
        )
    return {
        "session_id": session_id,
        "jti": jti,
        "expires_at": expires_at_dt.isoformat(timespec="seconds"),
    }


def _create_refresh_token(
    *,
    user_id: int,
    session_id: str,
    family_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    session: OrmSession | None = None,
) -> Dict[str, str]:
    now = datetime.now(timezone.utc)
    expires_at_dt = now + timedelta(days=max(1, int(REFRESH_TOKEN_TTL_DAYS)))
    token_id = f"rt-{uuid.uuid4().hex}"
    family = family_id or f"rf-{uuid.uuid4().hex}"
    secret = secrets.token_urlsafe(32)
    refresh_token = f"{token_id}.{secret}"
    token_hash = _sha256_hex(refresh_token)

    token_row = RefreshToken(
        token_id=token_id,
        user_id=int(user_id),
        session_id=str(session_id),
        family_id=family,
        token_hash=token_hash,
        created_at=now_utc_iso(),
        expires_at=expires_at_dt.isoformat(timespec="seconds"),
        used_at=None,
        revoked_at=None,
        replaced_by_token_id=None,
        ip_address=(ip_address or "")[:80] or None,
        user_agent=(user_agent or "")[:1000] or None,
    )
    if session is None:
        with session_scope() as db_session:
            db_session.add(token_row)
    else:
        session.add(token_row)

    return {
        "refresh_token": refresh_token,
        "token_id": token_id,
        "family_id": family,
        "expires_at": expires_at_dt.isoformat(timespec="seconds"),
    }


def _build_token(user: AuthUser, session_meta: Dict[str, str]) -> str:
    now = datetime.now(timezone.utc)
    exp = datetime.fromisoformat(session_meta["expires_at"])
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "sid": session_meta["session_id"],
        "jti": session_meta["jti"],
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": JWT_ISSUER,
    }
    return _jwt_encode(payload)


def authenticate_user(
    email: str,
    password: str,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
    mfa_code: str | None = None,
) -> AuthResult:
    normalized_email = _validate_email(email)
    _ensure_not_locked(normalized_email)

    with session_scope() as session:
        row = session.execute(
            select(User).where(User.email == normalized_email)
        ).scalar_one_or_none()

    if not row or not _verify_password(password, row.password_hash):
        _record_failed_attempt(normalized_email)
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    # If MFA is enabled, require a valid code (TOTP or backup code).
    try:
        from src.core.mfa_service import is_mfa_enabled, verify_mfa_code

        if is_mfa_enabled(int(row.id)):
            if not (mfa_code or "").strip():
                raise HTTPException(status_code=401, detail="MFA code required.")
            if not verify_mfa_code(int(row.id), str(mfa_code)):
                raise HTTPException(status_code=401, detail="Invalid MFA code.")
    except HTTPException:
        raise
    except Exception:
        # If MFA subsystem is unavailable, fail closed for enabled accounts.
        pass

    _clear_failed_attempts(normalized_email)

    user: AuthUser = {
        "id": int(row.id),
        "email": str(row.email),
        "name": str(row.name),
        "role": str(row.role),
    }
    session_meta = _create_session(
        user_id=int(row.id),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    refresh_meta = _create_refresh_token(
        user_id=int(row.id),
        session_id=session_meta["session_id"],
        ip_address=ip_address,
        user_agent=user_agent,
    )
    token = _build_token(user, session_meta)
    result: AuthResult = {
        "access_token": token,
        "refresh_token": refresh_meta["refresh_token"],
        "token_type": "bearer",
        "expires_at": session_meta["expires_at"],
        "user": user,
    }
    return result


def _is_session_active(payload: Dict[str, Any]) -> bool:
    session_id = str(payload.get("sid", ""))
    jti = str(payload.get("jti", ""))
    user_id = int(payload.get("sub", 0))
    if not session_id or not jti or user_id <= 0:
        return False

    with session_scope() as session:
        row = session.execute(
            select(AuthSession).where(
                AuthSession.session_id == session_id,
                AuthSession.jti == jti,
                AuthSession.user_id == user_id,
            )
        ).scalar_one_or_none()

    if not row:
        return False
    if row.revoked_at:
        return False
    try:
        expires_at = datetime.fromisoformat(row.expires_at)
        if datetime.now(timezone.utc) > expires_at:
            return False
    except Exception:
        return False
    return True


def revoke_token_session(token: str) -> None:
    payload = _jwt_decode(token)
    session_id = str(payload.get("sid", ""))
    jti = str(payload.get("jti", ""))
    user_id = int(payload.get("sub", 0))
    if not session_id or not jti or user_id <= 0:
        return
    with session_scope() as session:
        row = session.execute(
            select(AuthSession).where(
                AuthSession.session_id == session_id,
                AuthSession.jti == jti,
                AuthSession.user_id == user_id,
            )
        ).scalar_one_or_none()
        if not row:
            return
        row.revoked_at = now_utc_iso()
        tokens = (
            session.execute(
                select(RefreshToken).where(
                    RefreshToken.user_id == user_id,
                    RefreshToken.session_id == session_id,
                    RefreshToken.revoked_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        for token_row in tokens:
            token_row.revoked_at = now_utc_iso()


def session_meta_from_token(token: str) -> dict[str, str]:
    payload = _jwt_decode(token)
    return {
        "session_id": str(payload.get("sid", "")),
        "jti": str(payload.get("jti", "")),
    }


def list_sessions_for_user(user_id: int) -> list[dict[str, Any]]:
    uid = int(user_id)
    if uid <= 0:
        return []
    with session_scope() as session:
        rows = (
            session.execute(
                select(AuthSession)
                .where(AuthSession.user_id == uid)
                .order_by(AuthSession.created_at.desc())
            )
            .scalars()
            .all()
        )
    return [
        {
            "session_id": str(row.session_id),
            "created_at": str(row.created_at),
            "expires_at": str(row.expires_at),
            "revoked_at": str(row.revoked_at) if row.revoked_at else None,
            "ip_address": str(row.ip_address) if row.ip_address else None,
            "user_agent": str(row.user_agent) if row.user_agent else None,
        }
        for row in rows
    ]


def revoke_session_for_user(user_id: int, session_id: str) -> dict[str, str]:
    uid = int(user_id)
    sid = str(session_id or "").strip()
    if uid <= 0 or not sid:
        raise HTTPException(status_code=400, detail="Invalid request.")

    now_iso = now_utc_iso()
    with session_scope() as session:
        row = session.execute(
            select(AuthSession).where(AuthSession.user_id == uid, AuthSession.session_id == sid)
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found.")
        if not row.revoked_at:
            row.revoked_at = now_iso

        tokens = (
            session.execute(
                select(RefreshToken).where(
                    RefreshToken.user_id == uid,
                    RefreshToken.session_id == sid,
                    RefreshToken.revoked_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        for token_row in tokens:
            token_row.revoked_at = now_iso

    return {"status": "revoked", "session_id": sid}


def revoke_other_sessions_for_user(user_id: int, *, keep_session_id: str | None = None) -> None:
    uid = int(user_id)
    keep = str(keep_session_id or "").strip()
    if uid <= 0:
        return

    now_iso = now_utc_iso()
    with session_scope() as session:
        sessions = (
            session.execute(
                select(AuthSession).where(AuthSession.user_id == uid, AuthSession.revoked_at.is_(None))
            )
            .scalars()
            .all()
        )
        for row in sessions:
            if keep and str(row.session_id) == keep:
                continue
            row.revoked_at = now_iso

        tokens = (
            session.execute(
                select(RefreshToken).where(RefreshToken.user_id == uid, RefreshToken.revoked_at.is_(None))
            )
            .scalars()
            .all()
        )
        for row in tokens:
            if keep and str(row.session_id) == keep:
                continue
            row.revoked_at = now_iso


def update_user_profile(user_id: int, *, name: str) -> AuthUser:
    uid = int(user_id)
    safe_name = (name or "").strip()
    if uid <= 0 or len(safe_name) < 2:
        raise HTTPException(status_code=400, detail="Invalid profile update.")
    safe_name = safe_name[:100]

    with session_scope() as session:
        row = session.execute(select(User).where(User.id == uid)).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="User not found.")
        row.name = safe_name
        user: AuthUser = {
            "id": int(row.id),
            "email": str(row.email),
            "name": str(row.name),
            "role": str(row.role),
        }
        return user


def change_user_password(
    user_id: int,
    *,
    current_password: str,
    new_password: str,
    keep_session_id: str | None = None,
) -> dict[str, str]:
    uid = int(user_id)
    if uid <= 0:
        raise HTTPException(status_code=400, detail="Invalid user id.")

    if not verify_user_password(uid, current_password):
        raise HTTPException(status_code=401, detail="Invalid current password.")

    # Enforce password policy and rotate hash.
    _validate_password_strength(new_password)
    with session_scope() as session:
        row = session.execute(select(User).where(User.id == uid)).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="User not found.")
        row.password_hash = _password_hash(new_password)

    # Revoke all other sessions so existing tokens can't be reused.
    revoke_other_sessions_for_user(uid, keep_session_id=keep_session_id)
    return {"status": "changed"}


def revoke_all_sessions_for_user(user_id: int, *, session: OrmSession | None = None) -> None:
    uid = int(user_id)
    if uid <= 0:
        return

    now_iso = now_utc_iso()

    def _revoke(db: OrmSession) -> None:
        sessions = (
            db.execute(
                select(AuthSession).where(
                    AuthSession.user_id == uid,
                    AuthSession.revoked_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        for row in sessions:
            row.revoked_at = now_iso

        tokens = (
            db.execute(
                select(RefreshToken).where(
                    RefreshToken.user_id == uid,
                    RefreshToken.revoked_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        for row in tokens:
            row.revoked_at = now_iso

    if session is None:
        with session_scope() as db_session:
            _revoke(db_session)
    else:
        _revoke(session)


def refresh_session(
    refresh_token: str,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuthResult:
    token_value = (refresh_token or "").strip()
    if not token_value:
        raise HTTPException(status_code=401, detail="Refresh token required.")
    token_hash = _sha256_hex(token_value)

    now = datetime.now(timezone.utc)
    now_iso = now_utc_iso()

    with session_scope() as session:
        token_row = session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        ).scalar_one_or_none()
        if not token_row:
            raise HTTPException(status_code=401, detail="Invalid refresh token.")

        # Detect reuse: a previously used token appearing again.
        if token_row.used_at and not token_row.revoked_at:
            family = str(token_row.family_id)
            family_rows = (
                session.execute(
                    select(RefreshToken).where(
                        RefreshToken.user_id == token_row.user_id,
                        RefreshToken.family_id == family,
                        RefreshToken.revoked_at.is_(None),
                    )
                )
                .scalars()
                .all()
            )
            for row in family_rows:
                row.revoked_at = now_iso

            sess = session.execute(
                select(AuthSession).where(
                    AuthSession.user_id == token_row.user_id,
                    AuthSession.session_id == token_row.session_id,
                )
            ).scalar_one_or_none()
            if sess and not sess.revoked_at:
                sess.revoked_at = now_iso

            raise HTTPException(status_code=401, detail="Refresh token reuse detected. Please login again.")

        if token_row.revoked_at:
            raise HTTPException(status_code=401, detail="Refresh token is revoked.")
        try:
            expires_at_dt = datetime.fromisoformat(str(token_row.expires_at))
            if now > expires_at_dt:
                token_row.revoked_at = now_iso
                raise HTTPException(status_code=401, detail="Refresh token has expired.")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="Refresh token is invalid.")

        sess = session.execute(
            select(AuthSession).where(
                AuthSession.user_id == token_row.user_id,
                AuthSession.session_id == token_row.session_id,
            )
        ).scalar_one_or_none()
        if not sess or sess.revoked_at:
            raise HTTPException(status_code=401, detail="Session is expired or revoked.")
        try:
            session_exp = datetime.fromisoformat(str(sess.expires_at))
            if now > session_exp:
                raise HTTPException(status_code=401, detail="Session is expired or revoked.")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="Session is expired or revoked.")

        # Mark refresh token as used and rotate.
        token_row.used_at = now_iso

        # Rotate session jti and extend access token expiry on refresh.
        new_jti = uuid.uuid4().hex
        new_access_exp = (now + timedelta(minutes=TOKEN_TTL_MINUTES)).isoformat(timespec="seconds")
        sess.jti = new_jti
        sess.expires_at = new_access_exp

        refresh_meta = _create_refresh_token(
            user_id=int(token_row.user_id),
            session_id=str(token_row.session_id),
            family_id=str(token_row.family_id),
            ip_address=ip_address,
            user_agent=user_agent,
            session=session,
        )
        token_row.replaced_by_token_id = refresh_meta["token_id"]

        user_row = session.execute(
            select(User).where(User.id == token_row.user_id)
        ).scalar_one_or_none()
        if not user_row:
            raise HTTPException(status_code=401, detail="User not found.")

        user: AuthUser = {
            "id": int(user_row.id),
            "email": str(user_row.email),
            "name": str(user_row.name),
            "role": str(user_row.role),
        }
        access_token = _build_token(
            user,
            {
                "session_id": str(sess.session_id),
                "jti": str(sess.jti),
                "expires_at": str(sess.expires_at),
            },
        )

    result: AuthResult = {
        "access_token": access_token,
        "refresh_token": refresh_meta["refresh_token"],
        "token_type": "bearer",
        "expires_at": str(sess.expires_at),
        "user": user,
    }
    return result


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthUser:
    token: str | None = None
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    else:
        token = request.cookies.get(ACCESS_COOKIE_NAME) or request.cookies.get("access_token")

    if not token:
        api_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
        if api_key:
            return authenticate_api_key(api_key)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    payload = _jwt_decode(token)
    if not _is_session_active(payload):
        raise HTTPException(status_code=401, detail="Session is expired or revoked.")
    user: AuthUser = {
        "id": int(payload.get("sub", 0)),
        "email": str(payload.get("email", "")),
        "name": str(payload.get("name", "")),
        "role": str(payload.get("role", "user")),
    }
    return user


def require_role(role: str):
    def _dependency(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if user.get("role") != role:
            raise HTTPException(status_code=403, detail="Insufficient permissions.")
        return user

    return _dependency


ROLE_DEFAULT_PERMISSIONS: dict[str, set[str]] = {
    "user": {
        "analyze:run",
        "jobs:submit",
        "jobs:read",
        "rag:ask",
        "data:read",
    },
    "admin": {"*"},
}


def user_has_permission(user: AuthUser, permission: str) -> bool:
    perm = (permission or "").strip().lower()
    role = str(user.get("role", "user") or "user").lower()
    if not perm:
        return False

    defaults = ROLE_DEFAULT_PERMISSIONS.get(role, set())
    if "*" in defaults or perm in defaults:
        return True

    user_id = int(user.get("id", 0) or 0)
    if user_id <= 0:
        return False

    with session_scope() as session:
        rows = session.execute(
            select(UserPermission.permission).where(UserPermission.user_id == user_id)
        ).scalars().all()

    for item in rows:
        p = str(item or "").strip().lower()
        if not p:
            continue
        if p == "*" or p == perm:
            return True
        if p.endswith(":*") and perm.startswith(p[:-1]):
            return True
    return False


def require_permission(permission: str):
    def _dependency(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if not user_has_permission(user, permission):
            raise HTTPException(status_code=403, detail="Insufficient permissions.")
        return user

    return _dependency
