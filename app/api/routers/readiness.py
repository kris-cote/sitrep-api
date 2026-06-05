# app/api/routers/readiness.py
from __future__ import annotations

from fastapi import APIRouter
from datetime import datetime, timezone
import os

from app.observability.metrics import (
    hub_goes_available,
    hub_goes_image_age_seconds,
    hub_goes_image_size_bytes,
    hub_goes_last_updated_epoch,
    hub_goes_errors_total,
    hub_go_no_go_last_result,
    hub_go_no_go_last_evaluated_epoch,
    hub_go_no_go_checks_total,
    hub_go_no_go_checks_failed_total,
)

router = APIRouter()

GOES_CACHE_PATH = os.getenv("GOES_CACHE_PATH", "/app/data/goes_latest.jpg")
GOES_MAX_AGE_SECONDS = int(os.getenv("GOES_MAX_AGE_SECONDS", "1800"))  # 30 min default

def _now_epoch() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp())

def _stat_goes_cache() -> dict:
    try:
        if not os.path.exists(GOES_CACHE_PATH):
            return {"available": False, "size_bytes": 0, "age_seconds": None, "mtime_epoch": 0}
        size = os.path.getsize(GOES_CACHE_PATH)
        if size <= 0:
            return {"available": False, "size_bytes": 0, "age_seconds": None, "mtime_epoch": 0}
        mtime = int(os.path.getmtime(GOES_CACHE_PATH))
        age = max(0, _now_epoch() - mtime)
        return {"available": True, "size_bytes": size, "age_seconds": age, "mtime_epoch": mtime}
    except Exception:
        hub_goes_errors_total.inc()
        return {"available": False, "size_bytes": 0, "age_seconds": None, "mtime_epoch": 0}

@router.get("/go-no-go")
def go_no_go():
    hub_go_no_go_checks_total.inc()
    evaluated_epoch = _now_epoch()

    goes = _stat_goes_cache()

    # Update GOES gauges every run
    hub_goes_available.set(1 if goes["available"] else 0)
    hub_goes_image_size_bytes.set(int(goes["size_bytes"] or 0))
    hub_goes_last_updated_epoch.set(int(goes["mtime_epoch"] or 0))
    hub_goes_image_age_seconds.set(float(goes["age_seconds"] or 0))

    reasons = []
    decision_go = True

    if not goes["available"]:
        decision_go = False
        reasons.append("GOES cache missing or empty (hub-api).")

    if goes["age_seconds"] is not None and goes["age_seconds"] > GOES_MAX_AGE_SECONDS:
        decision_go = False
        reasons.append(f"GOES cache stale: age_seconds={goes['age_seconds']} > {GOES_MAX_AGE_SECONDS}.")

    # Publish decision gauges
    hub_go_no_go_last_result.set(1 if decision_go else 0)
    hub_go_no_go_last_evaluated_epoch.set(evaluated_epoch)

    if not decision_go:
        hub_go_no_go_checks_failed_total.inc()

    return {
        "decision": "GO" if decision_go else "NO_GO",
        "evaluated_epoch": evaluated_epoch,
        "checks": {
            "goes_available": bool(goes["available"]),
            "goes_size_bytes": int(goes["size_bytes"] or 0),
            "goes_age_seconds": goes["age_seconds"],
            "goes_last_updated_epoch": int(goes["mtime_epoch"] or 0),
            "goes_max_age_seconds": GOES_MAX_AGE_SECONDS,
        },
        "reasons": reasons,
    }
