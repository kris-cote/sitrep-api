from fastapi import Header, HTTPException
from typing import Optional
from app.core.config import settings

def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    print("HEADER:", repr(x_api_key), flush=True)
    print("EXPECTED:", repr(settings.hub_api_key_master), flush=True)
    if x_api_key != settings.hub_api_key_master:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key
