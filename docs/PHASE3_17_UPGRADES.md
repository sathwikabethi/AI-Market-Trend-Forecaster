# Phase 3 - 17 Upgrades Delivered

1. PostgreSQL-first database support via `DATABASE_URL` (SQLite fallback).
2. SQLAlchemy ORM data layer across auth, jobs, alerts, evaluations, and dataset store.
3. JWT authentication with secure password hashing.
4. Session-backed JWT controls (`sid`/`jti`) with logout revocation.
5. Role-based access control for admin routes.
6. Scheduled ingestion pipeline that queues ingestion jobs.
7. Manual ingestion trigger and ingestion run history endpoints.
8. Dataset version tracking with CSV snapshots.
9. Preprocessing audit trail in DB + CSV.
10. Model evaluation history tracking and admin visibility.
11. KPI threshold alerts persisted and exposed to admin.
12. In-memory caching for trends/product/data status APIs.
13. Optional Redis-backed queue path for worker dispatch.
14. Structured JSON logging with request correlation.
15. Request metadata (`X-Request-ID`, response timing), security headers, and rate limiting.
16. Metrics exports in JSON + Prometheus and optional OpenTelemetry tracing hooks.
17. Delivery automation: CI workflow + Docker/Docker Compose stack.
