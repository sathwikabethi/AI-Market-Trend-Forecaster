from __future__ import annotations

import os
import json
import asyncio
import time
import uuid
import hashlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.analytics.business_metrics import compute_business_kpis
from src.api.schemas import (
    AdminOverviewResponse,
    AlertResponse,
    AnalyzeJobRequest,
    AnalyzeResponse,
    AuthResponse,
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyItem,
    ApiKeyRevokeRequest,
    ApiKeyRevokeResponse,
    DashboardOverviewResponse,
    DashboardReviewItem,
    DataStatusResponse,
    EmailVerificationConfirmRequest,
    EmailVerificationConfirmResponse,
    EmailVerificationRequest,
    EmailVerificationRequestResponse,
    ErrorResponse,
    HealthResponse,
    IngestionRunResponse,
    IngestionTriggerRequest,
    JobResponse,
    LoginRequest,
    LogoutResponse,
    MFAEnableRequest,
    MFADisableRequest,
    MFASetupResponse,
    MFAStatusResponse,
    PermissionChangeRequest,
    PasswordChangeRequest,
    ProductItem,
    PreprocessingAuditResponse,
    PasswordResetConfirmRequest,
    PasswordResetConfirmResponse,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    ProfileUpdateRequest,
    RefreshRequest,
    RAGAskRequest,
    RAGAskResponse,
    RegisterRequest,
    ReviewRequest,
    SessionItem,
    SessionRevokeRequest,
    StatusResponse,
    TrendPoint,
    TrendResponse,
    UserResponse,
)
from src.core import (
    allow_request,
    authenticate_user,
    cache_get,
    cache_set,
    cache_stats,
    create_default_admin_user,
    create_user,
    database_meta,
    ensure_database,
    evaluate_kpi_alerts,
    evaluate_model_quality,
    confirm_email_verification,
    confirm_password_reset,
    get_current_user,
    get_job,
    get_latest_evaluation,
    list_alerts,
    list_drift_runs,
    list_ingestion_runs,
    list_user_permissions,
    metrics_snapshot,
    prometheus_metrics,
    queue_stats,
    rate_limit_snapshot,
    refresh_session,
    request_email_verification,
    request_password_reset,
    run_drift_detection,
    grant_user_permission,
    revoke_token_session,
    revoke_user_permission,
    require_permission,
    require_role,
    settings,
    setup_tracing,
    start_ingestion_scheduler,
    start_job_worker,
    submit_analyze_job,
    trigger_ingestion_now,
    verify_user_password,
)
from src.core.auth import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    REFRESH_TOKEN_TTL_DAYS,
    TOKEN_TTL_MINUTES,
    AuthResult,
    AuthUser,
    change_user_password,
    create_api_key,
    list_api_keys,
    list_sessions_for_user,
    revoke_api_key,
    revoke_other_sessions_for_user,
    revoke_session_for_user,
    session_meta_from_token,
    update_user_profile,
)
from src.core.audit import list_security_audit_logs, log_security_event
from src.core.cache import cache_invalidate_prefix
from src.core.metrics import increment, observe_duration
from src.core.mfa_service import begin_mfa_setup, disable_mfa, enable_mfa, is_mfa_enabled
from src.data_processing import (
    append_review,
    dataset_versions,
    initialize_datasets,
    list_data_quality_runs,
    list_preprocessing_audits,
    list_products,
    product_trends,
    run_data_quality_checks,
)
from src.core.logging_config import configure_logging
from src.core.sentry import setup_sentry
from src.nlp.aspect_sentiment import aspect_sentiment_analysis
from src.rag import ask_rag, rag_status


SERVICE_NAME = "CareSense AI Backend"
SERVICE_VERSION = "2.0.0"

configure_logging()
logger = logging.getLogger("src.api.main")
SENTRY_ENABLED = setup_sentry()


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_database()
    create_default_admin_user()
    initialize_datasets(force_refresh=True)
    evaluate_model_quality(model_name="nlp_baseline")
    run_drift_detection(model_name="nlp_baseline")
    start_ingestion_scheduler()
    start_job_worker()
    yield


app = FastAPI(
    title=SERVICE_NAME,
    version=SERVICE_VERSION,
    description="Enterprise market trend and consumer sentiment backend.",
    lifespan=lifespan,
)


class ApiPrefixMiddleware:
    """Compatibility + versioning aliases.

    Supports calling the backend directly at:
    - /api/* (frontend proxy convention)
    - /api/v1/* and /v1/* (versioned aliases)

    while keeping the canonical routes defined without a prefix.
    """

    def __init__(self, app, **_: object):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        path = scope.get("path") or ""
        for prefix in ("/api/v1", "/v1", "/api"):
            if path == prefix or path.startswith(prefix + "/"):
                new_path = path[len(prefix) :] or "/"
                # Starlette treats scope as immutable; create a shallow copy.
                scope = dict(scope)
                scope["path"] = new_path
                scope["raw_path"] = new_path.encode("utf-8")
                break

        return await self.app(scope, receive, send)


app.add_middleware(ApiPrefixMiddleware)
TRACING_ENABLED = setup_tracing(app)
_logout_bearer = HTTPBearer(auto_error=False)


def _cors_origins() -> List[str]:
    raw_origins = os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).strip()
    if raw_origins == "*":
        return ["*"]
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


allowed_origins = _cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allowed_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _request_id_from(request: Request) -> str | None:
    request_id = getattr(request.state, "request_id", None)
    return str(request_id) if request_id else None


def _error_response(
    *,
    status_code: int,
    error: str,
    message: str,
    request_id: str | None = None,
    details: Dict[str, Any] | None = None,
) -> JSONResponse:
    payload_model = ErrorResponse(
        error=error,
        message=message,
        request_id=request_id,
        details=details,
    )
    payload = (
        payload_model.model_dump()
        if hasattr(payload_model, "model_dump")
        else payload_model.dict()
    )
    return JSONResponse(status_code=status_code, content=payload)


def _rating_from_aspects(aspects: Dict[str, Dict[str, Any]]) -> int:
    pos_scores = []
    neg_scores = []
    for aspect_result in aspects.values():
        if not isinstance(aspect_result, dict):
            continue
        scores = aspect_result.get("scores", {})
        if not isinstance(scores, dict):
            continue
        pos_scores.append(float(scores.get("positive", 0.0) or 0.0))
        neg_scores.append(float(scores.get("negative", 0.0) or 0.0))

    if not pos_scores:
        return 3
    pos_avg = sum(pos_scores) / len(pos_scores)
    neg_avg = sum(neg_scores) / len(neg_scores) if neg_scores else 0.0
    delta = pos_avg - neg_avg

    if delta >= 0.25:
        return 5
    if delta >= 0.08:
        return 4
    if delta <= -0.25:
        return 1
    if delta <= -0.08:
        return 2
    return 3


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()
    increment("http_requests_total", 1)
    increment(f"http_requests_{request.method}_{request.url.path}", 1)

    content_length = int(request.headers.get("content-length", "0") or 0)
    if content_length > int(settings.max_request_body_bytes):
        increment("http_request_too_large_total", 1)
        return _error_response(
            status_code=413,
            error="payload_too_large",
            message=f"Request body exceeds {settings.max_request_body_bytes} bytes.",
            request_id=request_id,
        )

    client = request.client.host if request.client else "unknown"
    limiter_key = f"{client}:{request.method}:{request.url.path}"
    if not allow_request(
        limiter_key,
        max_requests=settings.rate_limit_max_requests,
        window_seconds=settings.rate_limit_window_seconds,
    ):
        increment("http_rate_limited_total", 1)
        return _error_response(
            status_code=429,
            error="rate_limit_exceeded",
            message="Too many requests. Please retry later.",
            request_id=request_id,
        )

    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    increment(f"http_responses_{response.status_code}", 1)
    observe_duration("http_response_time_ms_total", elapsed_ms)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-ms"] = str(elapsed_ms)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    logger.info(
        "request_completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": elapsed_ms,
            "client": request.client.host if request.client else None,
        },
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    increment("http_validation_errors_total", 1)
    logger.warning(
        "request_validation_error",
        extra={
            "request_id": _request_id_from(request),
            "method": request.method,
            "path": request.url.path,
            "status_code": 422,
            "errors": exc.errors(),
        },
    )
    return _error_response(
        status_code=422,
        error="validation_error",
        message="Request validation failed.",
        request_id=_request_id_from(request),
        details={"errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    increment("http_unhandled_errors_total", 1)
    logger.exception(
        "unhandled_exception",
        extra={
            "request_id": _request_id_from(request),
            "method": request.method,
            "path": request.url.path,
            "status_code": 500,
        },
    )
    return _error_response(
        status_code=500,
        error="internal_server_error",
        message=str(exc) or "Unexpected server error.",
        request_id=_request_id_from(request),
    )


@app.get("/", response_model=HealthResponse)
def root() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=SERVICE_NAME,
        timestamp=datetime.now(timezone.utc),
        details={"version": SERVICE_VERSION},
    )


@app.get("/health/liveness", response_model=HealthResponse)
def health_liveness() -> HealthResponse:
    return HealthResponse(
        status="alive",
        service=SERVICE_NAME,
        timestamp=datetime.now(timezone.utc),
    )


@app.get("/health/readiness", response_model=HealthResponse)
def health_readiness() -> HealthResponse:
    status_data = initialize_datasets().as_dict()
    db_meta = database_meta()
    queue = queue_stats()
    return HealthResponse(
        status="ready",
        service=SERVICE_NAME,
        timestamp=datetime.now(timezone.utc),
        details={
            "database": db_meta,
            "raw_rows": status_data.get("raw_rows", 0),
            "processed_rows": status_data.get("processed_rows", 0),
            "redis_enabled": queue.get("redis_enabled", False),
            "tracing_enabled": TRACING_ENABLED,
            "sentry_enabled": SENTRY_ENABLED,
        },
    )


def _auth_cookie_config(request: Request) -> dict[str, Any]:
    raw_samesite = (os.environ.get("AUTH_COOKIE_SAMESITE", "lax") or "lax").strip().lower()
    samesite = raw_samesite if raw_samesite in {"lax", "strict", "none"} else "lax"

    raw_secure = os.environ.get("AUTH_COOKIE_SECURE")
    if raw_secure is None:
        secure = request.url.scheme == "https" or settings.app_env.strip().lower() == "production"
    else:
        secure = raw_secure.strip().lower() in {"1", "true", "yes", "on"}

    domain = (os.environ.get("AUTH_COOKIE_DOMAIN") or "").strip() or None
    return {"samesite": samesite, "secure": secure, "domain": domain}


def _set_auth_cookies(response: Response, request: Request, auth: AuthResult) -> None:
    config = _auth_cookie_config(request)
    # Keep cookie TTLs aligned with server-side token TTLs.
    access_max_age = max(60, int(TOKEN_TTL_MINUTES) * 60)
    refresh_max_age = max(3600, int(REFRESH_TOKEN_TTL_DAYS) * 24 * 60 * 60)

    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=auth["access_token"],
        httponly=True,
        secure=config["secure"],
        samesite=config["samesite"],
        max_age=access_max_age,
        domain=config["domain"],
        path="/",
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=auth["refresh_token"],
        httponly=True,
        secure=config["secure"],
        samesite=config["samesite"],
        max_age=refresh_max_age,
        domain=config["domain"],
        path="/",
    )


def _clear_auth_cookies(response: Response, request: Request) -> None:
    config = _auth_cookie_config(request)
    response.delete_cookie(key=ACCESS_COOKIE_NAME, domain=config["domain"], path="/")
    response.delete_cookie(key=REFRESH_COOKIE_NAME, domain=config["domain"], path="/")


@app.post("/auth/register", response_model=AuthResponse)
def register(payload: RegisterRequest, request: Request, response: Response) -> AuthResponse:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        create_user(payload.email, payload.name, payload.password, role="user")
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        status_code = getattr(exc, "status_code", 500)
        log_security_event(
            event_type="auth.register",
            status="failure",
            actor_email=payload.email,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"detail": detail, "status_code": status_code},
        )
        raise

    auth: AuthResult = authenticate_user(
        payload.email,
        payload.password,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    log_security_event(
        event_type="auth.register",
        status="success",
        actor_user_id=int(auth["user"]["id"]),
        actor_email=str(auth["user"]["email"]),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    _set_auth_cookies(response, request, auth)
    return AuthResponse(
        access_token=auth["access_token"],
        refresh_token=auth["refresh_token"],
        token_type=auth["token_type"],
        expires_at=auth["expires_at"],
        user=UserResponse(**auth["user"]),
    )


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, response: Response) -> AuthResponse:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        auth: AuthResult = authenticate_user(
            payload.email,
            payload.password,
            ip_address=ip_address,
            user_agent=user_agent,
            mfa_code=payload.mfa_code,
        )
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        status_code = getattr(exc, "status_code", 500)
        log_security_event(
            event_type="auth.login",
            status="failure",
            actor_email=payload.email,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"detail": detail, "status_code": status_code},
        )
        raise

    log_security_event(
        event_type="auth.login",
        status="success",
        actor_user_id=int(auth["user"]["id"]),
        actor_email=str(auth["user"]["email"]),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    _set_auth_cookies(response, request, auth)
    return AuthResponse(
        access_token=auth["access_token"],
        refresh_token=auth["refresh_token"],
        token_type=auth["token_type"],
        expires_at=auth["expires_at"],
        user=UserResponse(**auth["user"]),
    )


@app.get("/auth/me", response_model=UserResponse)
def me(user: AuthUser = Depends(get_current_user)) -> UserResponse:
    return UserResponse(**user)


@app.patch("/auth/profile", response_model=UserResponse)
def update_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> UserResponse:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    updated = update_user_profile(int(user.get("id", 0) or 0), name=payload.name)
    log_security_event(
        event_type="auth.profile.update",
        status="success",
        actor_user_id=int(updated.get("id", 0) or 0) or None,
        actor_email=str(updated.get("email", "")) or None,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return UserResponse(**updated)


@app.post("/auth/password/change", response_model=StatusResponse)
def password_change(
    payload: PasswordChangeRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_logout_bearer),
    user: AuthUser = Depends(get_current_user),
) -> StatusResponse:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    token = None
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if not token:
        token = request.cookies.get(ACCESS_COOKIE_NAME) or request.cookies.get("access_token")

    keep_session_id = None
    if token:
        try:
            keep_session_id = session_meta_from_token(token).get("session_id") or None
        except Exception:
            keep_session_id = None

    try:
        result = change_user_password(
            int(user.get("id", 0) or 0),
            current_password=payload.current_password,
            new_password=payload.new_password,
            keep_session_id=keep_session_id,
        )
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        status_code = getattr(exc, "status_code", 500)
        log_security_event(
            event_type="auth.password.change",
            status="failure",
            actor_user_id=int(user.get("id", 0) or 0) or None,
            actor_email=str(user.get("email", "")) or None,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"detail": detail, "status_code": status_code},
        )
        raise

    log_security_event(
        event_type="auth.password.change",
        status="success",
        actor_user_id=int(user.get("id", 0) or 0) or None,
        actor_email=str(user.get("email", "")) or None,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return StatusResponse(status=str(result.get("status") or "changed"))


@app.get("/auth/sessions", response_model=List[SessionItem])
def list_sessions(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_logout_bearer),
    user: AuthUser = Depends(get_current_user),
) -> List[SessionItem]:
    token = None
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if not token:
        token = request.cookies.get(ACCESS_COOKIE_NAME) or request.cookies.get("access_token")

    current_session_id = ""
    if token:
        try:
            current_session_id = session_meta_from_token(token).get("session_id") or ""
        except Exception:
            current_session_id = ""

    rows = list_sessions_for_user(int(user.get("id", 0) or 0))
    result: List[SessionItem] = []
    for row in rows:
        row_session_id = str(row.get("session_id", ""))
        result.append(
            SessionItem(
                session_id=row_session_id,
                created_at=str(row.get("created_at") or ""),
                expires_at=str(row.get("expires_at") or ""),
                revoked_at=row.get("revoked_at"),
                ip_address=row.get("ip_address"),
                user_agent=row.get("user_agent"),
                is_current=bool(current_session_id and row_session_id == current_session_id),
            )
        )
    return result


@app.post("/auth/sessions/revoke", response_model=StatusResponse)
def revoke_session(
    payload: SessionRevokeRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_logout_bearer),
    user: AuthUser = Depends(get_current_user),
) -> StatusResponse:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    token = None
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if not token:
        token = request.cookies.get(ACCESS_COOKIE_NAME) or request.cookies.get("access_token")

    current_session_id = ""
    if token:
        try:
            current_session_id = session_meta_from_token(token).get("session_id") or ""
        except Exception:
            current_session_id = ""

    if current_session_id and payload.session_id == current_session_id:
        raise HTTPException(status_code=400, detail="Use logout to revoke the current session.")

    try:
        revoke_session_for_user(int(user.get("id", 0) or 0), payload.session_id)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        status_code = getattr(exc, "status_code", 500)
        log_security_event(
            event_type="auth.sessions.revoke",
            status="failure",
            actor_user_id=int(user.get("id", 0) or 0) or None,
            actor_email=str(user.get("email", "")) or None,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"detail": detail, "status_code": status_code, "session_id": payload.session_id},
        )
        raise

    log_security_event(
        event_type="auth.sessions.revoke",
        status="success",
        actor_user_id=int(user.get("id", 0) or 0) or None,
        actor_email=str(user.get("email", "")) or None,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"session_id": payload.session_id},
    )
    return StatusResponse(status="revoked")


@app.post("/auth/sessions/revoke-all", response_model=StatusResponse)
def revoke_all_sessions(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_logout_bearer),
    user: AuthUser = Depends(get_current_user),
) -> StatusResponse:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    token = None
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if not token:
        token = request.cookies.get(ACCESS_COOKIE_NAME) or request.cookies.get("access_token")

    keep_session_id = None
    if token:
        try:
            keep_session_id = session_meta_from_token(token).get("session_id") or None
        except Exception:
            keep_session_id = None

    revoke_other_sessions_for_user(int(user.get("id", 0) or 0), keep_session_id=keep_session_id)
    log_security_event(
        event_type="auth.sessions.revoke_all",
        status="success",
        actor_user_id=int(user.get("id", 0) or 0) or None,
        actor_email=str(user.get("email", "")) or None,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"keep_session_id": keep_session_id},
    )
    return StatusResponse(status="revoked")


@app.get("/auth/api-keys", response_model=List[ApiKeyItem])
def api_keys_list(user: AuthUser = Depends(get_current_user)) -> List[ApiKeyItem]:
    rows = list_api_keys(int(user.get("id", 0) or 0))
    return [ApiKeyItem(**row) for row in rows]


@app.post("/auth/api-keys", response_model=ApiKeyCreateResponse)
def api_keys_create(
    payload: ApiKeyCreateRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> ApiKeyCreateResponse:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    result = create_api_key(int(user.get("id", 0) or 0), payload.name)
    log_security_event(
        event_type="auth.api_keys.create",
        status="success",
        actor_user_id=int(user.get("id", 0) or 0) or None,
        actor_email=str(user.get("email", "")) or None,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"key_id": result.get("key_id"), "name": result.get("name")},
    )
    return ApiKeyCreateResponse(**result)


@app.post("/auth/api-keys/revoke", response_model=ApiKeyRevokeResponse)
def api_keys_revoke(
    payload: ApiKeyRevokeRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> ApiKeyRevokeResponse:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    result = revoke_api_key(int(user.get("id", 0) or 0), payload.key_id)
    log_security_event(
        event_type="auth.api_keys.revoke",
        status="success",
        actor_user_id=int(user.get("id", 0) or 0) or None,
        actor_email=str(user.get("email", "")) or None,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"key_id": payload.key_id},
    )
    return ApiKeyRevokeResponse(**result)


@app.post("/auth/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(_logout_bearer),
) -> LogoutResponse:
    token = None
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if not token:
        token = request.cookies.get(ACCESS_COOKIE_NAME) or request.cookies.get("access_token")

    user: AuthUser | None = None
    try:
        user = get_current_user(request=request, credentials=credentials)
    except Exception:
        user = None

    log_security_event(
        event_type="auth.logout",
        status="success",
        actor_user_id=int(user.get("id", 0) or 0) if user else None,
        actor_email=str(user.get("email", "")) if user else None,
        details={"action": "logout"},
    )
    if token:
        try:
            revoke_token_session(token)
        except Exception:
            # Best-effort revoke; still clear cookies.
            pass

    _clear_auth_cookies(response, request)
    return LogoutResponse(status="logged_out")


@app.post("/auth/refresh", response_model=AuthResponse)
def refresh(payload: RefreshRequest, request: Request, response: Response) -> AuthResponse:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    token_value = (payload.refresh_token or "").strip()
    if not token_value:
        token_value = (request.cookies.get(REFRESH_COOKIE_NAME) or "").strip()
    try:
        auth: AuthResult = refresh_session(
            token_value,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        status_code = getattr(exc, "status_code", 500)
        log_security_event(
            event_type="auth.refresh",
            status="failure",
            ip_address=ip_address,
            user_agent=user_agent,
            details={"detail": detail, "status_code": status_code},
        )
        raise

    log_security_event(
        event_type="auth.refresh",
        status="success",
        actor_user_id=int(auth["user"]["id"]),
        actor_email=str(auth["user"]["email"]),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    _set_auth_cookies(response, request, auth)
    return AuthResponse(
        access_token=auth["access_token"],
        refresh_token=auth["refresh_token"],
        token_type=auth["token_type"],
        expires_at=auth["expires_at"],
        user=UserResponse(**auth["user"]),
    )


@app.get("/auth/mfa/status", response_model=MFAStatusResponse)
def mfa_status(user: AuthUser = Depends(get_current_user)) -> MFAStatusResponse:
    return MFAStatusResponse(enabled=is_mfa_enabled(int(user.get("id", 0) or 0)))


@app.post("/auth/mfa/setup", response_model=MFASetupResponse)
def mfa_setup(request: Request, user: AuthUser = Depends(get_current_user)) -> MFASetupResponse:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    actor_email = str(user.get("email", "")) or None
    try:
        payload = begin_mfa_setup(
            int(user.get("id", 0) or 0),
            issuer="CareSense AI",
            account_name=str(user.get("email", "")),
        )
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        status_code = getattr(exc, "status_code", 500)
        log_security_event(
            event_type="auth.mfa.setup",
            status="failure",
            actor_user_id=int(user.get("id", 0) or 0) or None,
            actor_email=actor_email,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"detail": detail, "status_code": status_code},
        )
        raise

    log_security_event(
        event_type="auth.mfa.setup",
        status="success",
        actor_user_id=int(user.get("id", 0) or 0) or None,
        actor_email=actor_email,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return MFASetupResponse(**payload)


@app.post("/auth/mfa/enable")
def mfa_enable(
    payload: MFAEnableRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    actor_email = str(user.get("email", "")) or None
    try:
        result = enable_mfa(int(user.get("id", 0) or 0), payload.code)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        status_code = getattr(exc, "status_code", 500)
        log_security_event(
            event_type="auth.mfa.enable",
            status="failure",
            actor_user_id=int(user.get("id", 0) or 0) or None,
            actor_email=actor_email,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"detail": detail, "status_code": status_code},
        )
        raise

    log_security_event(
        event_type="auth.mfa.enable",
        status="success",
        actor_user_id=int(user.get("id", 0) or 0) or None,
        actor_email=actor_email,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"status": result.get("status")},
    )
    return result


@app.post("/auth/mfa/disable")
def mfa_disable(
    payload: MFADisableRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    actor_email = str(user.get("email", "")) or None

    if not verify_user_password(int(user.get("id", 0) or 0), payload.password):
        log_security_event(
            event_type="auth.mfa.disable",
            status="failure",
            actor_user_id=int(user.get("id", 0) or 0) or None,
            actor_email=actor_email,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"detail": "Invalid password."},
        )
        raise HTTPException(status_code=401, detail="Invalid password.")

    result = disable_mfa(int(user.get("id", 0) or 0))
    log_security_event(
        event_type="auth.mfa.disable",
        status="success",
        actor_user_id=int(user.get("id", 0) or 0) or None,
        actor_email=actor_email,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"status": result.get("status")},
    )
    return result


@app.post("/auth/email/verification/request", response_model=EmailVerificationRequestResponse)
def email_verification_request(payload: EmailVerificationRequest, request: Request) -> EmailVerificationRequestResponse:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        result = request_email_verification(email=payload.email)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        status_code = getattr(exc, "status_code", 500)
        log_security_event(
            event_type="auth.email_verification.request",
            status="failure",
            actor_email=payload.email,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"detail": detail, "status_code": status_code},
        )
        raise

    log_security_event(
        event_type="auth.email_verification.request",
        status="success",
        actor_email=payload.email,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"status": result.get("status")},
    )
    return EmailVerificationRequestResponse(**result)


@app.post("/auth/email/verification/confirm", response_model=EmailVerificationConfirmResponse)
def email_verification_confirm(
    payload: EmailVerificationConfirmRequest,
    request: Request,
) -> EmailVerificationConfirmResponse:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        result = confirm_email_verification(token=payload.token)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        status_code = getattr(exc, "status_code", 500)
        log_security_event(
            event_type="auth.email_verification.confirm",
            status="failure",
            ip_address=ip_address,
            user_agent=user_agent,
            details={"detail": detail, "status_code": status_code},
        )
        raise

    log_security_event(
        event_type="auth.email_verification.confirm",
        status="success",
        ip_address=ip_address,
        user_agent=user_agent,
        details={"status": result.get("status")},
    )
    return EmailVerificationConfirmResponse(**result)


@app.post("/auth/password/reset/request", response_model=PasswordResetRequestResponse)
def password_reset_request(payload: PasswordResetRequest, request: Request) -> PasswordResetRequestResponse:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        result = request_password_reset(email=payload.email)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        status_code = getattr(exc, "status_code", 500)
        log_security_event(
            event_type="auth.password_reset.request",
            status="failure",
            actor_email=payload.email,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"detail": detail, "status_code": status_code},
        )
        raise

    log_security_event(
        event_type="auth.password_reset.request",
        status="success",
        actor_email=payload.email,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"status": result.get("status")},
    )
    return PasswordResetRequestResponse(**result)


@app.post("/auth/password/reset/confirm", response_model=PasswordResetConfirmResponse)
def password_reset_confirm(
    payload: PasswordResetConfirmRequest,
    request: Request,
) -> PasswordResetConfirmResponse:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        result = confirm_password_reset(token=payload.token, new_password=payload.new_password)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        status_code = getattr(exc, "status_code", 500)
        log_security_event(
            event_type="auth.password_reset.confirm",
            status="failure",
            ip_address=ip_address,
            user_agent=user_agent,
            details={"detail": detail, "status_code": status_code},
        )
        raise

    log_security_event(
        event_type="auth.password_reset.confirm",
        status="success",
        ip_address=ip_address,
        user_agent=user_agent,
        details={"status": result.get("status")},
    )
    return PasswordResetConfirmResponse(**result)


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(review: ReviewRequest, request: Request) -> AnalyzeResponse:
    aspects = aspect_sentiment_analysis(review.text)
    kpis = compute_business_kpis(aspects)
    alerts = evaluate_kpi_alerts(kpis)
    rating = _rating_from_aspects(aspects)
    append_review(
        text=review.text,
        product=review.product or "general",
        source="api",
        rating=rating,
        request_id=_request_id_from(request),
    )
    cache_invalidate_prefix("trends:")
    cache_invalidate_prefix("status:")
    return AnalyzeResponse(aspects=aspects, business_kpis=kpis, alerts=alerts)


@app.post("/jobs/analyze")
def analyze_async(
    payload: AnalyzeJobRequest,
    user: AuthUser = Depends(get_current_user),
):
    job_id = submit_analyze_job(
        text=payload.text,
        product=payload.product or "general",
        requested_by=str(user.get("email", "")),
        idempotency_key=payload.idempotency_key,
    )
    return {"job_id": job_id, "status": "pending"}


@app.post("/ingestion/run")
def run_ingestion(
    payload: IngestionTriggerRequest,
    user: AuthUser = Depends(require_permission("admin:ingestion")),
):
    log_security_event(
        event_type="ingestion.trigger",
        status="success",
        actor_user_id=int(user.get("id", 0) or 0) or None,
        actor_email=str(user.get("email", "")) or None,
        details={
            "source": payload.source,
            "batch_size": payload.batch_size,
            "connector": payload.connector,
        },
    )
    run_id = trigger_ingestion_now(
        source=payload.source,
        batch_size=payload.batch_size,
        connector=payload.connector,
    )
    return {"run_id": run_id, "status": "queued"}


@app.get("/ingestion/runs", response_model=List[IngestionRunResponse])
def ingestion_runs(
    limit: int = 50,
    user: AuthUser = Depends(require_permission("admin:ingestion")),
) -> List[IngestionRunResponse]:
    rows = list_ingestion_runs(limit=limit)
    return [IngestionRunResponse(**row) for row in rows]


@app.get("/jobs/{job_id}", response_model=JobResponse)
def job_status(job_id: str, user: AuthUser = Depends(get_current_user)) -> JobResponse:
    job = get_job(job_id)
    if not job:
        return JobResponse(
            job_id=job_id,
            job_type="analyze_review",
            status="not_found",
            payload="{}",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    return JobResponse(**job)


@app.get("/products", response_model=List[ProductItem])
def get_products() -> List[ProductItem]:
    cached = cache_get("products:list")
    if cached is not None:
        return [ProductItem(**row) for row in cached]
    rows = list_products()
    cache_set("products:list", rows, ttl_seconds=120)
    return [ProductItem(**row) for row in rows]


@app.get("/trends", response_model=TrendResponse)
def get_trends(product: str = Query(..., min_length=1, max_length=100)) -> TrendResponse:
    key = f"trends:{product.lower().strip()}"
    cached = cache_get(key)
    if cached is not None:
        return TrendResponse(product=product, trends=cached)
    raw_trends = product_trends(product)
    trends = [TrendPoint(**row) for row in raw_trends]
    cache_set(key, trends, ttl_seconds=120)
    return TrendResponse(product=product, trends=trends)


@app.get("/dashboard/overview", response_model=DashboardOverviewResponse)
def dashboard_overview(
    product: str | None = Query(default=None, min_length=1, max_length=100),
    topic: str | None = Query(default=None, min_length=1, max_length=80),
    days: int = Query(default=7, ge=1, le=60),
    source_mix: str | None = Query(default=None, min_length=1, max_length=240),
    refresh: bool = Query(default=False),
    user: AuthUser = Depends(get_current_user),
) -> DashboardOverviewResponse:
    _ = user
    from src.analytics.dashboard import dashboard_overview as build_dashboard_overview

    safe_product = (product or "all").strip().lower() or "all"
    safe_topic = (topic or "all").strip().lower() or "all"
    mix_raw = (source_mix or "").strip()
    mix_key = "none"
    if mix_raw:
        mix_key = hashlib.sha1(mix_raw.encode("utf-8")).hexdigest()[:12]
    key = f"dashboard:overview:{safe_product}:{int(days or 7)}:{safe_topic}:{mix_key}"
    if not refresh:
        cached = cache_get(key)
        if cached is not None:
            return DashboardOverviewResponse(**cached)
    payload = build_dashboard_overview(product=product, days=days, topic=topic, source_mix=source_mix)
    cache_set(key, payload, ttl_seconds=20)
    return DashboardOverviewResponse(**payload)


@app.get("/dashboard/reviews", response_model=List[DashboardReviewItem])
def dashboard_reviews(
    product: str | None = Query(default=None, min_length=1, max_length=100),
    topic: str | None = Query(default=None, min_length=1, max_length=80),
    source: str | None = Query(default=None, min_length=1, max_length=40),
    region: str | None = Query(default=None, min_length=2, max_length=4),
    days: int = Query(default=7, ge=1, le=60),
    limit: int = Query(default=60, ge=1, le=200),
    user: AuthUser = Depends(get_current_user),
) -> List[DashboardReviewItem]:
    _ = user
    from src.analytics.dashboard import list_dashboard_reviews as build_review_list

    rows = build_review_list(
        product=product,
        days=days,
        topic=topic,
        source=source,
        region=region,
        limit=limit,
    )
    return [DashboardReviewItem(**row) for row in rows]


@app.get("/data/status", response_model=DataStatusResponse)
def data_status() -> DataStatusResponse:
    key = "status:data"
    cached = cache_get(key)
    if cached is not None:
        return DataStatusResponse(**cached)
    status_data = initialize_datasets().as_dict()
    cache_set(key, status_data, ttl_seconds=30)
    return DataStatusResponse(**status_data)


@app.get("/data/versions")
def data_versions(limit: int = 20):
    return dataset_versions(limit=limit)


@app.get("/data/preprocessing-audits", response_model=List[PreprocessingAuditResponse])
def data_preprocessing_audits(limit: int = 20) -> List[PreprocessingAuditResponse]:
    rows = list_preprocessing_audits(limit=limit)
    return [PreprocessingAuditResponse(**row) for row in rows]


@app.post("/data/quality/run")
def data_quality_run(
    user: AuthUser = Depends(require_permission("data:quality")),
):
    _ = user
    return run_data_quality_checks(note="manual")


@app.get("/data/quality/runs")
def data_quality_runs(
    limit: int = 20,
    user: AuthUser = Depends(require_permission("data:quality")),
):
    _ = user
    return list_data_quality_runs(limit=limit)


@app.get("/admin/alerts", response_model=List[AlertResponse])
def admin_alerts(
    limit: int = 50,
    user: AuthUser = Depends(require_permission("admin:alerts")),
):
    rows = list_alerts(limit=limit)
    return [AlertResponse(**row) for row in rows]


@app.post("/admin/drift/run")
def admin_run_drift(
    user: AuthUser = Depends(require_permission("admin:drift")),
):
    _ = user
    return run_drift_detection(model_name="nlp_baseline")


@app.get("/admin/drift/runs")
def admin_list_drift(
    limit: int = 20,
    user: AuthUser = Depends(require_permission("admin:drift")),
):
    _ = user
    return list_drift_runs(limit=limit)


@app.get("/admin/overview", response_model=AdminOverviewResponse)
def admin_overview(user: AuthUser = Depends(require_permission("admin:overview"))):
    status_data = DataStatusResponse(**initialize_datasets().as_dict())
    latest_eval = get_latest_evaluation()
    alerts = [AlertResponse(**row) for row in list_alerts(limit=20)]
    preprocess_audits = [
        PreprocessingAuditResponse(**row) for row in list_preprocessing_audits(limit=20)
    ]
    ingestion_runs = [IngestionRunResponse(**row) for row in list_ingestion_runs(limit=20)]
    return AdminOverviewResponse(
        data_status=status_data,
        latest_evaluation=latest_eval,
        alerts=alerts,
        preprocessing_audits=preprocess_audits,
        ingestion_runs=ingestion_runs,
        drift_runs=list_drift_runs(limit=20),
        data_quality_runs=list_data_quality_runs(limit=20),
        security_audit_logs=list_security_audit_logs(limit=20),
        cache=cache_stats(),
        metrics=metrics_snapshot(),
        queue=queue_stats(),
        versions=dataset_versions(limit=20),
    )


@app.get("/metrics")
def metrics():
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics_snapshot(),
        "cache": cache_stats(),
        "rate_limit": rate_limit_snapshot(),
        "queue": queue_stats(),
        "environment": settings.app_env,
    }


@app.get("/metrics/prometheus")
def metrics_prometheus():
    return PlainTextResponse(content=prometheus_metrics(), media_type="text/plain; version=0.0.4")


@app.get("/admin/analytics/stream")
async def admin_analytics_stream(
    request: Request,
    interval_ms: int = Query(default=2000, ge=250, le=60000),
    user: AuthUser = Depends(require_permission("admin:analytics")),
):
    _ = user

    async def _event_stream():
        # Tell the browser how long it should wait before retrying a dropped connection.
        yield f"retry: {int(interval_ms)}\n\n"
        while True:
            if await request.is_disconnected():
                return

            # Keep payload cheap since this can run long-lived.
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "environment": settings.app_env,
                "metrics": metrics_snapshot(),
                "cache": cache_stats(),
                "rate_limit": rate_limit_snapshot(),
                "queue": await asyncio.to_thread(queue_stats),
            }
            yield f"event: snapshot\ndata: {json.dumps(payload, default=str)}\n\n"
            await asyncio.sleep(max(0.25, float(interval_ms) / 1000.0))

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            # Important for browsers + reverse proxies.
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Disable Nginx proxy buffering (also set in Nginx config as defense-in-depth).
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/queue/status")
def queue_status(user: AuthUser = Depends(require_permission("admin:queue"))):
    _ = user
    return queue_stats()


@app.get("/rag/status")
def rag_status_endpoint():
    return rag_status()


@app.post("/rag/ask", response_model=RAGAskResponse)
def rag_ask_endpoint(
    payload: RAGAskRequest,
    user: AuthUser = Depends(get_current_user),
) -> RAGAskResponse:
    _ = user
    result = ask_rag(payload.question, product=payload.product, top_k=payload.top_k)
    return RAGAskResponse(**result)


@app.get("/export/raw")
def export_raw(user: AuthUser = Depends(require_permission("admin:export"))):
    initialize_datasets()
    log_security_event(
        event_type="admin.export_raw",
        status="success",
        actor_user_id=int(user.get("id", 0) or 0) or None,
        actor_email=str(user.get("email", "")) or None,
    )
    return FileResponse(path=str(initialize_datasets().raw_path), filename="reviews_raw.csv")


@app.get("/export/processed")
def export_processed(user: AuthUser = Depends(require_permission("admin:export"))):
    initialize_datasets()
    log_security_event(
        event_type="admin.export_processed",
        status="success",
        actor_user_id=int(user.get("id", 0) or 0) or None,
        actor_email=str(user.get("email", "")) or None,
    )
    return FileResponse(
        path=str(initialize_datasets().processed_path),
        filename="cleaned_reviews.csv",
    )


@app.get("/admin/security/audit-logs")
def admin_audit_logs(
    limit: int = 50,
    user: AuthUser = Depends(require_permission("admin:security_audit")),
):
    _ = user
    return list_security_audit_logs(limit=limit)


@app.get("/admin/security/permissions")
def admin_list_permissions(
    email: str,
    user: AuthUser = Depends(require_permission("admin:permissions")),
):
    _ = user
    return {"email": email, "permissions": list_user_permissions(email)}


@app.post("/admin/security/permissions/grant")
def admin_grant_permission(
    payload: PermissionChangeRequest,
    user: AuthUser = Depends(require_permission("admin:permissions")),
):
    _ = user
    log_security_event(
        event_type="admin.permissions.grant",
        status="success",
        actor_user_id=int(user.get("id", 0) or 0) or None,
        actor_email=str(user.get("email", "")) or None,
        details={"target_email": payload.email, "permission": payload.permission},
    )
    return grant_user_permission(payload.email, payload.permission)


@app.post("/admin/security/permissions/revoke")
def admin_revoke_permission(
    payload: PermissionChangeRequest,
    user: AuthUser = Depends(require_permission("admin:permissions")),
):
    _ = user
    log_security_event(
        event_type="admin.permissions.revoke",
        status="success",
        actor_user_id=int(user.get("id", 0) or 0) or None,
        actor_email=str(user.get("email", "")) or None,
        details={"target_email": payload.email, "permission": payload.permission},
    )
    return revoke_user_permission(payload.email, payload.permission)
