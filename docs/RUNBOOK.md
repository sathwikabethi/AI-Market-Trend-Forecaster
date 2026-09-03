# Operations Runbook

## Start Services
```bash
python run_project.py
```

Manual start:
```bash
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8002 --reload
cd frontend && npm run dev -- --host=127.0.0.1 --port=5173
```

## Production (Nginx)
- Deployment guide: `docs/NGINX_DEPLOYMENT.md`
- Nginx template: `deploy/nginx/caresense.conf`

## Health Checks
- Liveness: `GET /health/liveness`
- Readiness: `GET /health/readiness`
- Metrics: `GET /metrics`
- Prometheus metrics: `GET /metrics/prometheus`

## Common Checks
```bash
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m compileall src
cd frontend && npm run lint && npm run build
```

## Data Verification
- Raw dataset: `data/raw/reviews_raw.csv`
- Processed dataset: `data/processed/cleaned_reviews.csv`
- Preprocessing audit log: `data/processed/preprocessing_audit_log.csv`
- Model evaluation history: `data/processed/model_evaluation_history.csv`

## Ingestion Controls
- Trigger ingestion job (admin): `POST /ingestion/run`
- Check ingestion runs (admin): `GET /ingestion/runs`
- Queue status (admin): `GET /queue/status`

## RAG Controls
- RAG index status: `GET /rag/status`
- Ask review-grounded question (auth required): `POST /rag/ask`

## Admin Validation
- Login as admin user
- Open Admin panel
- Validate:
  - dataset counts
  - latest model evaluation
  - preprocessing audits
  - alert feed
