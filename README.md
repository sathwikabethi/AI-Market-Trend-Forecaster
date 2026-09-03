# CareSense AI - Market Trend and Sentiment Platform

Enterprise-ready full-stack project with:
- React + Tailwind frontend (login-first flow, unified home workspace)
- FastAPI backend (auth, NLP analysis, KPIs, admin APIs)
- NLP sentiment/aspect analysis with resilient fallbacks
- PostgreSQL-first data pipeline (SQLite fallback) with raw/processed datasets, versioning, and preprocessing audits
- Optional Redis-backed queue path for jobs + OpenTelemetry instrumentation hooks
- RAG query layer over processed review data (`/rag/ask`)

## Project Structure
- `src/api` - FastAPI app and schemas
- `src/nlp` - sentiment/aspect/explainability modules
- `src/data_processing` - dataset preprocessing and trend aggregation
- `src/core` - auth, cache, jobs, metrics, logging, evaluation
- `frontend` - Vite + React + Tailwind app
- `data/raw` and `data/processed` - generated datasets and audit artifacts

## Run Locally

### 1) Backend
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
# For fully pinned (reproducible) installs, use:
# pip install -r requirements.lock.txt
# Optional: set DATABASE_URL for PostgreSQL
# set DATABASE_URL=postgresql+psycopg://market_user:market_pass@127.0.0.1:5432/market_trend
# Optional: enable Redis queue path
# set REDIS_URL=redis://127.0.0.1:6379/0
# Optional: enable OpenTelemetry traces
# set OTEL_ENABLED=1
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8002 --reload
```

### 2) Frontend
```bash
cd frontend
npm install
npm run dev -- --host=127.0.0.1 --port=5173
```

### 3) One-command startup
```bash
python run_project.py
```

## Docker Run
```bash
docker compose up --build
```

Backend: `http://127.0.0.1:8002`  
Frontend: `http://127.0.0.1:5173`

## API Highlights
- `GET /health/liveness`
- `GET /health/readiness`
- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`
- `POST /auth/logout`
- `POST /analyze`
- `POST /jobs/analyze`
- `GET /jobs/{job_id}`
- `POST /ingestion/run` (admin)
- `GET /ingestion/runs` (admin)
- `GET /products`
- `GET /trends?product=<id>`
- `GET /data/status`
- `GET /data/versions`
- `GET /data/preprocessing-audits`
- `GET /admin/overview`
- `GET /admin/alerts`
- `GET /queue/status` (admin)
- `GET /rag/status`
- `POST /rag/ask`
- `GET /metrics/prometheus`

## Quality Checks
```bash
# Backend tests + compile
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m compileall src

# Frontend lint + build
cd frontend
npm run lint
npm run build
```

## Operations Docs
- [ROADMAP.md](ROADMAP.md)
- [docs/PHASE3_17_UPGRADES.md](docs/PHASE3_17_UPGRADES.md)
- [docs/SLOs.md](docs/SLOs.md)
- [docs/RUNBOOK.md](docs/RUNBOOK.md)
- [docs/INCIDENT_PLAYBOOK.md](docs/INCIDENT_PLAYBOOK.md)
