# TRL Mapping (Target: TRL-4)

## TRL-4 Definition (practical)
Component validation in a lab environment with:
- reproducible build
- stable interfaces (API contracts)
- testable evidence (logs, snapshots, tests)
- clear separation of polling vs decision logic

## What "done" means for TRL-4 here
- `docker compose up` reliably brings up Postgres + hub-api + pollers
- `/api/v1/health` returns OK
- Decision endpoint(s) return stable JSON based on cached inputs
- Pollers write at least one artifact/cached record successfully (weather/NOTAM already doing this)
- Smoke test script passes end-to-end

## What is explicitly NOT required at TRL-4
- Production reliability/SLA
- Full security hardening
- Full coverage dashboards
- Multi-tenant isolation complete
