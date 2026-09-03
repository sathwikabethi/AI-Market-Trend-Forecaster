from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: str
    message: str
    request_id: str | None = None
    details: Dict[str, Any] | None = None


class ReviewRequest(BaseModel):
    text: str = Field(..., min_length=3, max_length=8000)
    product: str | None = Field(default=None, min_length=1, max_length=100)


class AnalyzeResponse(BaseModel):
    aspects: Dict[str, Dict[str, Any]]
    business_kpis: Dict[str, float]
    alerts: List[Dict[str, Any]] = Field(default_factory=list)


class ProductItem(BaseModel):
    id: str
    name: str


class TrendPoint(BaseModel):
    date: str
    sentiment_score: float
    volume: int


class TrendResponse(BaseModel):
    product: str
    trends: List[TrendPoint]


class DataStatusResponse(BaseModel):
    raw_path: str
    processed_path: str
    raw_rows: int
    processed_rows: int


class PreprocessingAuditResponse(BaseModel):
    run_id: str
    created_at: str
    raw_rows: int
    processed_rows: int
    rows_with_empty_text: int
    avg_clean_token_count: float
    note: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime
    details: Dict[str, Any] | None = None


class RegisterRequest(BaseModel):
    email: str
    name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=10, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=6, max_length=128)
    mfa_code: str | None = Field(default=None, min_length=6, max_length=16)


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str


class ProfileUpdateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=6, max_length=128)
    new_password: str = Field(..., min_length=10, max_length=128)


class StatusResponse(BaseModel):
    status: str


class SessionItem(BaseModel):
    session_id: str
    created_at: str
    expires_at: str
    revoked_at: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    is_current: bool = False


class SessionRevokeRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=240)


class ApiKeyCreateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)


class ApiKeyCreateResponse(BaseModel):
    api_key: str
    key_id: str
    name: str
    prefix: str
    created_at: str


class ApiKeyItem(BaseModel):
    key_id: str
    name: str
    prefix: str
    created_at: str
    last_used_at: str | None = None
    revoked_at: str | None = None


class ApiKeyRevokeRequest(BaseModel):
    key_id: str = Field(..., min_length=3, max_length=240)


class ApiKeyRevokeResponse(BaseModel):
    status: str
    key_id: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_at: str | None = None
    user: UserResponse


class AuthCookieResponse(BaseModel):
    """Auth response when tokens are delivered via HttpOnly cookies."""

    expires_at: str | None = None
    user: UserResponse


class LogoutResponse(BaseModel):
    status: str


class RefreshRequest(BaseModel):
    refresh_token: str | None = Field(default=None, min_length=20, max_length=4000)


class DashboardKpiItem(BaseModel):
    helper: str
    label: str
    value: str
    progress: float = Field(..., ge=0.0, le=100.0)
    accent: str | None = None


class DashboardTrendPoint(BaseModel):
    day: str
    value: float


class DashboardTrendLine(BaseModel):
    key: str
    label: str
    color: str
    data: List[DashboardTrendPoint]


class DashboardTrend(BaseModel):
    mode: str = Field(..., pattern="^(single|multi)$")
    lines: List[DashboardTrendLine] | None = None
    line: DashboardTrendLine | None = None


class DashboardSentimentItem(BaseModel):
    label: str
    value: int = Field(..., ge=0, le=100)
    color: str


class DashboardSentiment(BaseModel):
    center_value: str
    center_label: str
    items: List[DashboardSentimentItem]


class DashboardRegionItem(BaseModel):
    code: str
    label: str
    value: int = Field(..., ge=0, le=100)


class DashboardSourceItem(BaseModel):
    key: str
    label: str
    value: int = Field(..., ge=0, le=100)
    tone: str = "slate"


class DashboardTopicItem(BaseModel):
    label: str
    highlighted: bool = False


class DashboardOverviewResponse(BaseModel):
    range_days: int = Field(..., ge=1, le=60)
    product: str | None = None
    title: str
    subtitle: str
    kpis: List[DashboardKpiItem]
    trend: DashboardTrend
    sentiment: DashboardSentiment
    regions: List[DashboardRegionItem]
    sources: List[DashboardSourceItem]
    topics: List[DashboardTopicItem]


class DashboardReviewItem(BaseModel):
    review_id: str
    date: str
    product: str
    product_name: str
    source: str
    rating: int
    sentiment_label: str
    sentiment_score: float
    review_text: str


class MFAStatusResponse(BaseModel):
    enabled: bool


class MFASetupResponse(BaseModel):
    secret_base32: str
    otpauth_url: str
    backup_codes: List[str]


class MFAEnableRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=16)


class MFADisableRequest(BaseModel):
    password: str = Field(..., min_length=6, max_length=128)


class EmailVerificationRequest(BaseModel):
    email: str


class EmailVerificationRequestResponse(BaseModel):
    status: str
    token: str | None = None
    token_id: str | None = None
    expires_at: str | None = None


class EmailVerificationConfirmRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=4000)


class EmailVerificationConfirmResponse(BaseModel):
    status: str
    email_verified_at: str | None = None


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetRequestResponse(BaseModel):
    status: str
    token: str | None = None
    token_id: str | None = None
    expires_at: str | None = None


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=4000)
    new_password: str = Field(..., min_length=10, max_length=128)


class PasswordResetConfirmResponse(BaseModel):
    status: str


class PermissionChangeRequest(BaseModel):
    email: str
    permission: str = Field(..., min_length=3, max_length=160)


class AnalyzeJobRequest(BaseModel):
    text: str = Field(..., min_length=3, max_length=8000)
    product: str | None = Field(default=None, min_length=1, max_length=100)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=160)


class IngestionTriggerRequest(BaseModel):
    source: str = Field(default="manual", min_length=2, max_length=50)
    batch_size: int = Field(default=4, ge=1, le=100)
    connector: str | None = Field(default=None, min_length=2, max_length=30)


class IngestionRunResponse(BaseModel):
    id: int
    run_id: str
    source: str
    status: str
    started_at: str
    completed_at: str | None = None
    details: str | None = None


class JobResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    idempotency_key: str | None = None
    payload: str
    attempts: int = 0
    max_attempts: int = 0
    available_at: str | None = None
    result: str | None = None
    dead_letter_reason: str | None = None
    error: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class AlertResponse(BaseModel):
    id: int
    created_at: str
    level: str
    code: str
    message: str
    payload: str | None = None


class AdminOverviewResponse(BaseModel):
    data_status: DataStatusResponse
    latest_evaluation: Dict[str, Any] | None = None
    alerts: List[AlertResponse]
    preprocessing_audits: List[PreprocessingAuditResponse]
    ingestion_runs: List[IngestionRunResponse]
    drift_runs: List[Dict[str, Any]] = Field(default_factory=list)
    data_quality_runs: List[Dict[str, Any]] = Field(default_factory=list)
    security_audit_logs: List[Dict[str, Any]] = Field(default_factory=list)
    cache: Dict[str, Any]
    metrics: Dict[str, Any]
    queue: Dict[str, Any]
    versions: List[Dict[str, Any]]


class RAGAskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=400)
    product: str | None = Field(default=None, min_length=1, max_length=100)
    top_k: int = Field(default=5, ge=1, le=10)


class RAGRetrievedItem(BaseModel):
    review_id: str
    product: str
    product_name: str
    date: str
    sentiment_label: str
    score: float
    snippet: str


class RAGAskResponse(BaseModel):
    question: str
    product: str | None = None
    answer: str
    retrieved: List[RAGRetrievedItem]
    summary: Dict[str, Any]
