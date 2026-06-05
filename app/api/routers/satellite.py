from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os

router = APIRouter(prefix="/api/v1/satellite", tags=["satellite"])

GOES_CACHE_PATH = os.getenv("GOES_CACHE_PATH", "/app/data/goes_latest.jpg")


@router.get("/goes/latest.jpg")
def goes_latest_jpg(sector: str = "pnw"):
    if not os.path.exists(GOES_CACHE_PATH) or os.path.getsize(GOES_CACHE_PATH) == 0:
        raise HTTPException(status_code=404, detail="GOES image not cached yet.")

    return FileResponse(
        GOES_CACHE_PATH,
        media_type="image/jpeg",
        filename="goes_latest.jpg",
    )
