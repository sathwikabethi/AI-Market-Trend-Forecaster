from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except Exception:
        return default


@dataclass(frozen=True)
class Settings:
    app_env: str = os.environ.get("APP_ENV", "development")
    log_level: str = os.environ.get("LOG_LEVEL", "INFO")
    rate_limit_window_seconds: int = _env_int("RATE_LIMIT_WINDOW_SECONDS", 60)
    rate_limit_max_requests: int = _env_int("RATE_LIMIT_MAX_REQUESTS", 180)
    max_request_body_bytes: int = _env_int("MAX_REQUEST_BODY_BYTES", 512_000)
    ingestion_scheduler_enabled: bool = _env_bool("INGESTION_SCHEDULER_ENABLED", True)
    ingestion_interval_seconds: int = _env_int("INGESTION_INTERVAL_SECONDS", 900)
    ingestion_batch_size: int = _env_int("INGESTION_BATCH_SIZE", 4)
    redis_url: str = os.environ.get("REDIS_URL", "").strip()
    redis_job_queue_name: str = os.environ.get("REDIS_JOB_QUEUE_NAME", "market.jobs")
    otel_enabled: bool = _env_bool("OTEL_ENABLED", False)
    otel_service_name: str = os.environ.get("OTEL_SERVICE_NAME", "caresense-api")
    otel_exporter_otlp_endpoint: str = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    otel_exporter_otlp_insecure: bool = _env_bool("OTEL_EXPORTER_OTLP_INSECURE", True)
    auth_max_failed_attempts: int = _env_int("AUTH_MAX_FAILED_ATTEMPTS", 5)
    auth_lockout_seconds: int = _env_int("AUTH_LOCKOUT_SECONDS", 600)
    auth_require_password_upper: bool = _env_bool("AUTH_REQUIRE_PASSWORD_UPPER", True)
    auth_require_password_lower: bool = _env_bool("AUTH_REQUIRE_PASSWORD_LOWER", True)
    auth_require_password_digit: bool = _env_bool("AUTH_REQUIRE_PASSWORD_DIGIT", True)
    rag_max_chunks: int = _env_int("RAG_MAX_CHUNKS", 8)
    rag_min_similarity: float = _env_float("RAG_MIN_SIMILARITY", 0.12)
    rag_char_weight: float = _env_float("RAG_CHAR_WEIGHT", 0.25)


settings = Settings()
