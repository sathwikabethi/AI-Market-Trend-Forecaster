from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Iterator

from sqlalchemy import Float, Integer, String, Text, UniqueConstraint, create_engine, inspect, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "app.db"

_DB_LOCK = RLock()


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_database_url(raw_url: str | None) -> str:
    if not raw_url:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{DB_PATH.as_posix()}"

    value = raw_url.strip()
    if value.startswith("postgres://"):
        value = value.replace("postgres://", "postgresql+psycopg://", 1)
    elif value.startswith("postgresql://") and "+psycopg" not in value:
        value = value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


DATABASE_URL = _normalize_database_url(os.environ.get("DATABASE_URL"))


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="user")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    email_verified_at: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class UserPermission(Base):
    __tablename__ = "user_permissions"
    __table_args__ = (UniqueConstraint("user_id", "permission", name="uq_user_permission"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class ReviewRaw(Base):
    __tablename__ = "reviews_raw"

    review_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    date: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    product: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    review_text: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)


class ReviewProcessed(Base):
    __tablename__ = "reviews_processed"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    date: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    product: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    review_text: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_text: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment_label: Mapped[str] = mapped_column(String(20), nullable=False)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)
    processed_at: Mapped[str] = mapped_column(String(64), nullable=False)


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    version_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class PreprocessingAudit(Base):
    __tablename__ = "preprocessing_audits"

    run_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_with_empty_text: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_clean_token_count: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ModelEvaluation(Base):
    __tablename__ = "model_evaluations"

    run_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    coverage: Mapped[float] = mapped_column(Float, nullable=False)
    avg_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    positive_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    negative_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    neutral_ratio: Mapped[float] = mapped_column(Float, nullable=False)


class ModelDriftRun(Base):
    __tablename__ = "model_drift_runs"

    run_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metric: Mapped[str] = mapped_column(String(80), nullable=False, default="js_divergence")
    drift_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    baseline_start: Mapped[str] = mapped_column(String(20), nullable=False)
    baseline_end: Mapped[str] = mapped_column(String(20), nullable=False)
    recent_start: Mapped[str] = mapped_column(String(20), nullable=False)
    recent_end: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)


class Job(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    available_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default=now_utc_iso)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    dead_letter_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    started_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(64), nullable=True)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    started_at: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    session_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    jti: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    expires_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    revoked_at: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)


class UserMFA(Base):
    __tablename__ = "user_mfa"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    secret_base32: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    enabled_at: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    backup_codes_hashes: Mapped[str | None] = mapped_column(Text, nullable=True)


class OneTimeToken(Base):
    __tablename__ = "one_time_tokens"

    token_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    token_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    expires_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    used_at: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    token_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    family_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    expires_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    used_at: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    revoked_at: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    replaced_by_token_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)


class ApiKey(Base):
    __tablename__ = "api_keys"

    key_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    last_used_at: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    revoked_at: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class SecurityAuditLog(Base):
    __tablename__ = "security_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    actor_email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)


class DataQualityRun(Base):
    __tablename__ = "data_quality_runs"

    run_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    checks: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)


def _create_engine() -> Engine:
    connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    return create_engine(
        DATABASE_URL,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def get_engine() -> Engine:
    return engine


def get_session() -> Session:
    return SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _seed_products(session: Session) -> None:
    rows = [
        ("sunscreen", "Sunscreen"),
        ("moisturizer", "Moisturizer"),
        ("cleanser", "Cleanser"),
        ("serum", "Serum"),
        ("neutrogena", "Neutrogena"),
        ("la_roche_posay", "La Roche-Posay"),
        ("cerave", "CeraVe"),
        ("supergoop", "Supergoop!"),
        ("general", "General"),
    ]
    existing = {item[0] for item in session.execute(select(Product.id)).all()}
    for product_id, name in rows:
        if product_id not in existing:
            session.add(Product(id=product_id, name=name))


def _apply_light_migrations() -> None:
    """Minimal forward-only migrations for dev environments.

    We use `create_all()` for new tables but also need to add columns to existing tables
    (SQLite/Postgres) when the schema evolves.
    """

    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
    except Exception:
        return

    def _has_column(table: str, col: str) -> bool:
        try:
            return any(item.get("name") == col for item in inspector.get_columns(table))
        except Exception:
            return False

    if "jobs" in table_names:
        # Add P0 queue reliability fields if the DB was created before these existed.
        missing = [
            col
            for col in ("idempotency_key", "attempts", "max_attempts", "available_at", "dead_letter_reason")
            if not _has_column("jobs", col)
        ]
        if missing:
            now_default = now_utc_iso()
            try:
                with engine.begin() as conn:
                    if "idempotency_key" in missing:
                        conn.execute(text("ALTER TABLE jobs ADD COLUMN idempotency_key VARCHAR(160)"))
                        conn.execute(
                            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_jobs_idempotency_key ON jobs(idempotency_key)")
                        )
                    if "attempts" in missing:
                        conn.execute(text("ALTER TABLE jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0"))
                    if "max_attempts" in missing:
                        conn.execute(text("ALTER TABLE jobs ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3"))
                    if "available_at" in missing:
                        safe_default = now_default.replace("'", "''")
                        conn.execute(
                            text(
                                "ALTER TABLE jobs ADD COLUMN available_at VARCHAR(64) "
                                f"NOT NULL DEFAULT '{safe_default}'"
                            )
                        )
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_available_at ON jobs(available_at)"))
                    if "dead_letter_reason" in missing:
                        conn.execute(text("ALTER TABLE jobs ADD COLUMN dead_letter_reason TEXT"))
            except Exception:
                # Never prevent boot in development; worst case the operator resets the DB.
                return

    if "users" in table_names and not _has_column("users", "email_verified_at"):
        try:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN email_verified_at VARCHAR(64)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_email_verified_at ON users(email_verified_at)"))
        except Exception:
            return


def ensure_database() -> None:
    with _DB_LOCK:
        Base.metadata.create_all(bind=engine)
        _apply_light_migrations()
        with session_scope() as session:
            _seed_products(session)


def database_meta() -> dict[str, str]:
    if DATABASE_URL.startswith("sqlite"):
        return {"driver": "sqlite", "database": str(DB_PATH)}
    return {
        "driver": "postgresql",
        "database": make_url(DATABASE_URL).render_as_string(hide_password=True),
    }
