# Repository Upgrade Roadmap

## Phase 1: Production Foundations - Completed
- API request/response schemas and validation
- Standardized error payloads
- Liveness/readiness endpoints
- Request metadata headers (`X-Request-ID`, response timing)
- Improved local run orchestration (`run_project.py`)
- Baseline backend tests and KPI unit tests

## Phase 2: Data + Model Maturity - Completed
- Database-backed persistence with PostgreSQL-first support (SQLite fallback)
- Raw/processed dataset generation in `data/raw` and `data/processed`
- Dataset versioning snapshots and version endpoint
- Preprocessing audit trail (DB + CSV log)
- Model evaluation history tracking
- KPI threshold alerts
- Scheduled ingestion jobs with queue-backed execution and run history

## Phase 3: Platform + Scale - Completed (Baseline)
- JWT authentication and role-based authorization
- Background job worker for async NLP analysis
- Centralized settings for environment profiles
- In-memory caching for trend/data endpoints
- Structured logging and in-memory metrics endpoint
- Rate limiting + request-size guards
- Prometheus text metrics export
- Optional OpenTelemetry tracing instrumentation
- Optional Redis-backed queue dispatch
- CI workflow for backend tests and frontend lint/build
- Docker and Docker Compose setup for local container deployment

## Applied Hardening Add-ons
- Session-backed JWT revocation and logout endpoint.
- Login lockout controls for repeated failed authentication attempts.
- Queue status observability endpoint (`/queue/status`).
- RAG retrieval service over processed review corpus (`/rag/ask`, `/rag/status`).

## Phase 4: Enterprise Product Experience - Completed (Baseline)
- Login-first React flow with unified post-login home workspace
- Admin console for data status, alerts, model health, dataset versions, preprocessing audits
- Export workflows for raw and processed datasets
- Operations documentation:
  - `docs/SLOs.md`
  - `docs/RUNBOOK.md`
  - `docs/INCIDENT_PLAYBOOK.md`

## Next Iteration Candidates
- OpenTelemetry tracing backend + frontend correlation
- Persistent queue backend (Redis/Celery)
- Real external ingestion connectors (Reddit, YouTube, news APIs)
- Canary deployment and rollback automation
