#!/usr/bin/env bash
set -euo pipefail

echo "[reset] WARNING: this will remove hub-api and pollers containers (not postgres volume unless you remove it explicitly)."
COMPOSE_BAKE=false docker compose rm -sf hub-api hub-pollers || true

echo "[reset] Removing cached artifacts in hub-data volume (if present)..."
# No alpine pull required: use an existing local container image if you have one.
# If this fails due to no image, you can skip; it's optional cleanup.
docker run --rm -v hub_hub-data:/data python:3.12-slim-bookworm bash -lc 'rm -f /data/goes_latest.* /data/_probe.txt || true; ls -la /data || true' || true

echo "[reset] Done."
