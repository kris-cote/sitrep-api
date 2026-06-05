#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE_URL:-http://localhost:9000}"

echo "[smoke] Checking health..."
curl -fsS "$BASE/api/v1/health" | python3 -m json.tool >/dev/null
echo "[smoke] health OK"

echo "[smoke] Checking OpenAPI..."
curl -fsS "$BASE/openapi.json" >/dev/null
echo "[smoke] openapi OK"

echo "[smoke] Checking satellite summary..."
curl -fsS "$BASE/api/v1/satellite/summary?area_id=bc" | python3 -m json.tool >/dev/null
echo "[smoke] satellite summary OK"

echo "[smoke] Checking GOES meta endpoint..."
curl -fsS "$BASE/api/v1/satellite/goes/latest.json?sector=pnw" | python3 -m json.tool >/dev/null
echo "[smoke] goes latest.json OK"

echo "[smoke] Done."
