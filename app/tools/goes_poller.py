#!/usr/bin/env python3
from __future__ import annotations

import os, json, time, re
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


DEFAULT_SECTOR = os.getenv("GOES_SECTOR", "pnw").strip()
DEFAULT_SAT = os.getenv("GOES_SAT", "G18").strip()         # common: G18 / G17 on NESDIS pages
DEFAULT_PRODUCT = os.getenv("GOES_PRODUCT", "GEOCOLOR").strip()
CACHE_JPG = os.getenv("GOES_CACHE_PATH", "/data/goes_latest.jpg")
CACHE_META = os.getenv("GOES_META_PATH", "/data/goes_latest.json")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

# timeouts matter in your environment (you've seen TLS handshakes stall)
REQ_TIMEOUT = float(os.getenv("GOES_HTTP_TIMEOUT", "20"))
UA = os.getenv("GOES_UA", "SpaceHub/1.0 (+https://sixthsenseai.ca)")

SECTOR_PAGE = "https://www.star.nesdis.noaa.gov/GOES/sector.php"

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def atomic_write(path: str, data: bytes) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)

def atomic_write_text(path: str, text: str) -> None:
    atomic_write(path, text.encode("utf-8"))

def find_best_image_url(html: str) -> str | None:
    """
    NESDIS sector pages usually reference CDN images.
    We try:
      1) <img src="...jpg">
      2) any .jpg/.jpeg in page scripts
    """
    soup = BeautifulSoup(html, "html.parser")
    # prioritize images that look like "latest" or GEOCOLOR
    candidates: list[str] = []
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if src and (".jpg" in src or ".jpeg" in src):
            candidates.append(src)

    # also scan raw html for jpgs
    candidates += re.findall(r'https?://[^\s"\'<>]+?\.(?:jpg|jpeg)', html, flags=re.I)

    # de-dup preserve order
    seen = set()
    uniq = []
    for c in candidates:
        if c not in seen:
            uniq.append(c); seen.add(c)

    # heuristic: prefer those containing GEOCOLOR or sector-ish tokens
    prefer = []
    for u in uniq:
        score = 0
        if "GEOCOLOR" in u.upper(): score += 5
        if "geocolor" in u.lower(): score += 5
        if "sector" in u.lower(): score += 1
        if "latest" in u.lower(): score += 2
        prefer.append((score, u))
    prefer.sort(key=lambda x: x[0], reverse=True)

    if prefer:
        return prefer[0][1]

    return None

def fetch_sector_page(sector: str, sat: str, product: str) -> str:
    params = {"sector": sector, "sat": sat, "product": product}
    r = requests.get(SECTOR_PAGE, params=params, timeout=REQ_TIMEOUT, headers={"User-Agent": UA})
    r.raise_for_status()
    return r.text

def fetch_image_bytes(url: str) -> bytes:
    # allow relative urls
    full = url if url.startswith("http") else urljoin(SECTOR_PAGE, url)
    r = requests.get(full, timeout=REQ_TIMEOUT, headers={"User-Agent": UA})
    r.raise_for_status()
    return r.content

def run_once(sector: str, sat: str, product: str) -> dict:
    meta: dict = {
        "sector": sector,
        "sat": sat,
        "product": product,
        "status": "MISSING",
        "fetched_at": None,
        "source_image_url": None,
        "bytes": 0,
        "cache_jpg": CACHE_JPG,
        "cache_meta": CACHE_META,
    }

    try:
        html = fetch_sector_page(sector, sat, product)
        img_url = find_best_image_url(html)
        meta["source_image_url"] = img_url

        if not img_url:
            meta["status"] = "MISSING"
            return meta

        img = fetch_image_bytes(img_url)

        # basic validity check
        if len(img) < 10_000:  # GOES images should be far bigger than this
            meta["status"] = "ERROR"
            meta["error"] = f"Image too small ({len(img)} bytes)"
            return meta

        os.makedirs(os.path.dirname(CACHE_JPG), exist_ok=True)
        atomic_write(CACHE_JPG, img)

        meta["status"] = "OK"
        meta["bytes"] = len(img)
        meta["fetched_at"] = now_iso()

        # if you serve externally:
        if PUBLIC_BASE_URL:
            meta["public_image_url"] = f"{PUBLIC_BASE_URL}/api/v1/satellite/goes/latest.jpg?sector={sector}"
            meta["public_meta_url"] = f"{PUBLIC_BASE_URL}/api/v1/satellite/goes/latest.json?sector={sector}"

        atomic_write_text(CACHE_META, json.dumps(meta, indent=2))

        return meta

    except Exception as e:
        meta["status"] = "ERROR"
        meta["error"] = f"{type(e).__name__}: {e}"
        # still write meta so API can explain what's wrong
        try:
            atomic_write_text(CACHE_META, json.dumps(meta, indent=2))
        except Exception:
            pass
        return meta

if __name__ == "__main__":
    sector = os.getenv("GOES_SECTOR", DEFAULT_SECTOR)
    sat = os.getenv("GOES_SAT", DEFAULT_SAT)
    product = os.getenv("GOES_PRODUCT", DEFAULT_PRODUCT)

    result = run_once(sector, sat, product)
    print(f"goes_poller: {result.get('status')} sector={sector} bytes={result.get('bytes')} fetched_at={result.get('fetched_at')}")
