from __future__ import annotations

import csv
import io
import re
import zipfile
from typing import Any, Dict, Optional

import httpx
from sqlmodel import Session, select

from app.models.exposure import ExposureAsset

STATCAN_POP_CENTRES_2021_ZIP = "https://www150.statcan.gc.ca/n1/tbl/csv/98100011-eng.zip"
DEFAULT_TIMEOUT_SECONDS = 30.0


class PopulationFeedError(RuntimeError):
    pass


def _norm(value: str) -> str:
    value = re.sub(r"\([^)]*\)", " ", value or "")
    value = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return " ".join(value.split())


def _pick(row: Dict[str, Any], *names: str) -> Optional[str]:
    lowered = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return str(value)
    return None


def _parse_population_rows(raw_zip: bytes) -> Dict[str, int]:
    try:
        with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
            csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
            if not csv_names:
                raise PopulationFeedError("Statistics Canada archive contained no CSV")
            with zf.open(csv_names[0]) as fh:
                text = io.TextIOWrapper(fh, encoding="utf-8-sig", errors="replace")
                reader = csv.DictReader(text)
                result: Dict[str, int] = {}
                for row in reader:
                    geo = _pick(row, "GEO", "Geography", "Population centre")
                    stat = _pick(row, "Statistics", "Characteristic") or ""
                    value = _pick(row, "VALUE", "Value", "2021")
                    if not geo or value in (None, ""):
                        continue
                    # The table is long-format in current StatCan CSV exports.
                    if stat and "population" not in stat.lower():
                        continue
                    try:
                        population = int(float(str(value).replace(",", "")))
                    except ValueError:
                        continue
                    key = _norm(geo)
                    if key:
                        result[key] = max(population, result.get(key, 0))
                return result
    except (zipfile.BadZipFile, OSError) as exc:
        raise PopulationFeedError(str(exc)) from exc


async def fetch_population_centres() -> Dict[str, int]:
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(STATCAN_POP_CENTRES_2021_ZIP, headers={"User-Agent": "SitRep/2.7 PopulationConnector"})
            response.raise_for_status()
            return _parse_population_rows(response.content)
    except httpx.HTTPError as exc:
        raise PopulationFeedError(str(exc)) from exc


async def enrich_bc_community_population(session: Session, tenant_id: str = "default") -> Dict[str, Any]:
    population_by_geo = await fetch_population_centres()
    communities = session.exec(
        select(ExposureAsset)
        .where(ExposureAsset.tenant_id == tenant_id)
        .where(ExposureAsset.asset_type.in_(["community", "first_nations_community"]))
    ).all()

    updated = 0
    unmatched = 0
    samples = []
    for asset in communities:
        name_key = _norm(asset.name)
        population = population_by_geo.get(name_key)
        if population is None:
            # Conservative suffix/prefix match for common StatCan geography labels.
            candidates = [value for key, value in population_by_geo.items() if key == name_key or key.startswith(name_key + " ")]
            population = max(candidates) if candidates else None
        if population is None:
            unmatched += 1
            if len(samples) < 20:
                samples.append(asset.name)
            continue
        asset.population = int(population)
        props = dict(asset.properties or {})
        props["population_source"] = "Statistics Canada table 98-10-0011-01, 2021 Census"
        props["population_reference_year"] = 2021
        asset.properties = props
        session.add(asset)
        updated += 1

    session.commit()
    return {
        "source": "Statistics Canada 2021 population centres",
        "tenant_id": tenant_id,
        "community_assets": len(communities),
        "updated": updated,
        "unmatched": unmatched,
        "unmatched_sample": samples,
        "matching_policy": "normalized exact/prefix matches only; ambiguous matches are left unset",
    }
