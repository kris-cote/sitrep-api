# app/observability/metrics.py
from __future__ import annotations

from prometheus_client import Counter, Gauge, REGISTRY

# --------
# Helpers (avoid "Duplicated timeseries in CollectorRegistry")
# --------
def _get_or_create_gauge(name: str, documentation: str) -> Gauge:
    existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Gauge(name, documentation)

def _get_or_create_counter(name: str, documentation: str) -> Counter:
    existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Counter(name, documentation)

# --------
# GOES cache / ingestion metrics (hub-api viewpoint)
# --------
hub_goes_available = _get_or_create_gauge(
    "hub_goes_available",
    "1 if the latest GOES image is present and non-empty in the hub cache; else 0.",
)

hub_goes_image_age_seconds = _get_or_create_gauge(
    "hub_goes_image_age_seconds",
    "Age in seconds of the cached GOES image (now - mtime). Large value indicates stale/missing.",
)

hub_goes_image_size_bytes = _get_or_create_gauge(
    "hub_goes_image_size_bytes",
    "Size in bytes of the cached GOES image file.",
)

hub_goes_last_updated_epoch = _get_or_create_gauge(
    "hub_goes_last_updated_epoch",
    "Unix epoch seconds when the cached GOES image was last updated (file mtime). 0 if unknown.",
)

hub_goes_errors_total = _get_or_create_counter(
    "hub_goes_errors_total",
    "Count of GOES ingestion/cache update errors observed by hub-api.",
)

# --------
# Go / No-Go readiness metrics
# --------
hub_go_no_go_last_result = _get_or_create_gauge(
    "hub_go_no_go_last_result",
    "Last Go/No-Go decision: 1=GO, 0=NO-GO.",
)

hub_go_no_go_last_evaluated_epoch = _get_or_create_gauge(
    "hub_go_no_go_last_evaluated_epoch",
    "Unix epoch seconds when the Go/No-Go check was last evaluated.",
)

hub_go_no_go_checks_total = _get_or_create_counter(
    "hub_go_no_go_checks_total",
    "Total number of Go/No-Go evaluations executed.",
)

hub_go_no_go_checks_failed_total = _get_or_create_counter(
    "hub_go_no_go_checks_failed_total",
    "Total number of Go/No-Go evaluations that returned NO-GO or encountered an error.",
)
