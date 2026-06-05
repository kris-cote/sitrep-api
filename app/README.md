# Space Hub (TRL-4 Build)

This repository contains a laboratory (TRL-4) build of the Space Hub situation awareness and decision-support stack.

## What it does (non-confidential)
- Polls external sources (weather, NOTAM, satellite metadata) via a poller service
- Normalizes and stores/cache artifacts
- Exposes stable FastAPI endpoints for status and decision outputs

## Quick start
1) Validate + build + run:
   ./scripts/bootstrap.sh

2) Smoke test:
   ./scripts/smoke_test.sh

3) Contract tests:
   BASE_URL=http://localhost:9000 python3 -m unittest -v

## Structure
- docs/      TRL evidence, architecture, decision logic
- hub-api/   FastAPI service
- hub-pollers (or hub-api/tools) Polling jobs (fetch + normalize + store)
- scripts/   bootstrap & smoke tests
- tests/     API contract tests
- data/      example raw/processed artifact layout
