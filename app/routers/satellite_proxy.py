from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.responses import RedirectResponse, FileResponse

import os
import urllib.request
import json
from datetime import datetime, timezone
import os
from fastapi import HTTPException, Response

router = APIRouter()

GOES_CACHE_PATH = os.getenv("GOES_CACHE_PATH", "/app/data/goes_latest.jpg")
HUB_SAT_BASE = os.getenv("HUB_SAT_BASE", "http://hub-sat:8000")  # example

def _http_json(url: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

@router.head("/goes/latest.jpg", include_in_schema=False)
def goes_latest_head(sector: str = "pnw"):
    if not (os.path.exists(GOES_CACHE_PATH) and os.path.getsize(GOES_CACHE_PATH) > 0):
        raise HTTPException(status_code=404, detail="GOES image not cached yet.")

    size = os.path.getsize(GOES_CACHE_PATH)
    return Response(
        status_code=200,
        headers={
            "Content-Type": "image/jpeg",
            "Content-Length": str(size),
        },
    )

@router.get("/goes/latest.json")
def goes_latest_json(sector: str = "pnw"):

    # Prefer hub-sat metadata if available
    try:
        meta = _http_json(f"{HUB_SAT_BASE}/sat/goes/latest/metadata", timeout=10)
        status = "OK" if meta.get("available") else "MISSING"
        return {
            "sector": sector,
            "status": status,
            "fetched_at": meta.get("last_updated"),
            "source_image_url": None,
            "image_url": f"/api/v1/satellite/goes/latest.jpg?sector={sector}",
            "meta_url": "/api/v1/satellite/goes/meta",
            "size_bytes": meta.get("size_bytes"),
            "source": meta.get("source"),
        }
    except Exception:
        # Fallback: use local cached file stat
        if os.path.exists(GOES_CACHE_PATH) and os.path.getsize(GOES_CACHE_PATH) > 0:
            mtime = os.path.getmtime(GOES_CACHE_PATH)
            fetched_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
            return {
                "sector": sector,
                "status": "OK",
                "fetched_at": fetched_at,
                "source_image_url": None,
                "image_url": f"/api/v1/satellite/goes/latest.jpg?sector={sector}",
                "meta_url": "/api/v1/satellite/goes/meta",
                "size_bytes": os.path.getsize(GOES_CACHE_PATH),
                "source": "LOCAL_CACHE_FALLBACK",
            }

        return {
            "sector": sector,
            "status": "MISSING",
            "fetched_at": None,
            "source_image_url": None,
            "image_url": f"/api/v1/satellite/goes/latest.jpg?sector={sector}",
            "meta_url": "/api/v1/satellite/goes/meta",
        }

@router.get("/goes/latest.jpg")
def goes_latest_jpg(sector: str = "pnw"):
    update_goes_metrics(GOES_CACHE_PATH)
    if os.path.exists(GOES_CACHE_PATH) and os.path.getsize(GOES_CACHE_PATH) > 0:
        return FileResponse(GOES_CACHE_PATH, media_type="image/jpeg", filename="goes_latest.jpg")

    # fallback only if local cache missing
    return RedirectResponse(url=f"{HUB_SAT_BASE}/sat/goes/latest/image")

@router.get("/goes/meta")
def goes_meta():
    return {
        "hub_sat_base_url": HUB_SAT_BASE,
        "goes_cache_path": GOES_CACHE_PATH,
    }
