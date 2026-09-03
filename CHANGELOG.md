# CHANGELOG

## 2026-03-16 - Phase Completion Baseline

Summary:
- Completed roadmap baseline across phases 1-4 with backend platform hardening, frontend UX upgrades, and operations tooling.
- Added hardening pass for phase 3 with tracing hooks, Redis queue path, stricter auth sessions, and RAG integration.

Highlights:
- Backend:
  - Added PostgreSQL-first SQLAlchemy data layer (SQLite fallback).
  - Added FastAPI lifespan bootstrap, structured JSON logging, and request-level observability enhancements.
  - Added preprocessing audit trail (`preprocessing_audits` table + `data/processed/preprocessing_audit_log.csv`).
  - Added `/data/preprocessing-audits` endpoint and surfaced audits in `/admin/overview`.
  - Added ingestion scheduling APIs (`/ingestion/run`, `/ingestion/runs`) and queued ingestion jobs.
  - Added request rate limiting, request-size guard, security headers, and `/metrics/prometheus`.
  - Added coverage for auth/admin/data endpoints in test suite.
- Frontend:
  - Upgraded unified login-first UX and enhanced dashboard/admin views.
  - Added KPI alerts display and richer admin insights (model evaluation, versions, preprocessing audits).
  - Added working ESLint configuration and lint pipeline support.
- DevOps:
  - Added CI workflow (`.github/workflows/ci.yml`) for backend tests and frontend lint/build.
  - Added containerization support (`Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`).
  - Added operations docs (`docs/SLOs.md`, `docs/RUNBOOK.md`, `docs/INCIDENT_PLAYBOOK.md`).
  - Added `pytest.ini` to ensure stable test discovery in Windows/OneDrive environments.

## 2026-02-12 - Fixes & run

Summary:
- Made the FastAPI backend resilient to missing heavy ML dependencies by lazy-loading transformers and providing safe fallbacks.
- Fixed a TypeError in `get_sentiment()` by validating the pipeline output format and adding defensive handling for unexpected data.
- Made `explain_prediction()` lazy-load the tokenizer/model and return an empty list when unavailable.

Files changed:
- `src/api/main.py` - lazy imports inside endpoint for robustness.
- `src/nlp/bert_sentiment.py` - defensive parsing of pipeline output and safe fallback.
- `src/nlp/explainability.py` - lazy model loading and fallback.

How to reproduce locally:
1. Install lightweight dependencies:
```bash
python -m pip install fastapi uvicorn requests
```
2. (Optional, for real model behavior) Install PyTorch and transformers following official instructions.

Run servers:
```bash
# Backend
python -m uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8002
# Frontend
cd frontend && npm run dev
```

Notes:
- Until PyTorch/transformers are installed and models are downloaded, the API returns safe NEUTRAL fallbacks for sentiment scores and explainability may be limited.
