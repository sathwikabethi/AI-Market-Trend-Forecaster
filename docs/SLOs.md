# Service Level Objectives

## Scope
- Backend API (`src.api.main`)
- Frontend app delivery (`frontend`)
- NLP analysis and KPI endpoints

## Targets
- Availability: `99.5%` monthly for `/health/liveness` and `/health/readiness`
- API latency: `p95 < 800ms` for `/analyze`, `p95 < 300ms` for `/products` and `/trends`
- Error budget: `0.5%` monthly unavailability
- Data freshness: raw/processed datasets refreshed within `15 minutes` when scheduler is enabled

## Alerts
- High risk KPI (`KPI_HIGH_RISK`)
- Low satisfaction KPI (`KPI_LOW_SATISFACTION`)
- High uncertainty KPI (`KPI_HIGH_UNCERTAINTY`)

## Measurement
- `/metrics` for counters and response-time totals
- Structured request logs with request IDs
- `/admin/overview` for data/model/audit snapshots

