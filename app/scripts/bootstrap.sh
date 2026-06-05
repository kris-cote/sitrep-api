#!/usr/bin/env bash
set -euo pipefail

echo "[bootstrap] Validating docker compose file..."
docker compose config >/dev/null

echo "[bootstrap] Building core services..."
COMPOSE_BAKE=false docker compose build hub-api hub-pollers

echo "[bootstrap] Starting services..."
COMPOSE_BAKE=false docker compose up -d hub-postgres hub-api hub-pollers

echo "[bootstrap] Done."
echo "Next: ./scripts/smoke_test.sh"
