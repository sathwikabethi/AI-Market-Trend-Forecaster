# Incident Playbook

## Severity Levels
- `SEV-1`: Full outage (frontend or backend unavailable)
- `SEV-2`: Core flow degraded (`/analyze`, auth, or admin API unstable)
- `SEV-3`: Non-critical degradation (UI styling, delayed trends, non-blocking errors)

## Initial Response
1. Confirm impact using `/health/liveness`, `/health/readiness`, `/metrics`.
2. Check recent logs and error spikes.
3. Identify whether failure is backend, frontend, or data pipeline.

## Backend Recovery Steps
1. Restart backend process.
2. Verify DB file exists at `data/app.db`.
3. Validate API docs and smoke endpoints.
4. Confirm NLP endpoints return valid JSON.

## Frontend Recovery Steps
1. Restart Vite service.
2. Verify proxy target (`VITE_BACKEND_URL`) and `/api` routing.
3. Run `npm run build` and inspect warnings/errors.

## Data Pipeline Recovery
1. Check `data/raw/reviews_raw.csv` and `data/processed/cleaned_reviews.csv`.
2. Confirm preprocessing audits are being appended.
3. Trigger a manual `/analyze` request and verify row counts increase.

## Incident Closure
1. Document root cause and timeline.
2. Add regression tests for the failure mode.
3. Update `ROADMAP.md` and runbook if operational gaps were found.

