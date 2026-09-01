from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import httpx
from sqlmodel import Session, select

from app.models.infrastructure import InfrastructureFeature
from app.services.canada_infrastructure_import import JURISDICTIONS

NRWN_DIRECTORY = "https://ftp.maps.canada.ca/pub/nrcan_rncan/vector/geobase_nrwn_rfn/"
DEFAULT_TIMEOUT_SECONDS = 45.0
RAIL_JURISDICTIONS = {code for code in JURISDICTIONS if code not in {"PE", "NU"}}


class CanadaRailImportError(RuntimeError):
    pass


def _centroid(geometry: Dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    coords = geometry.get("coordinates") or []
    points: List[tuple[float, float]] = []
    def walk(value: Any) -> None:
        if isinstance(value, (list, tuple)):
            if len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
                points.append((float(value[0]), float(value[1])))
            else:
                for item in value:
                    walk(item)
    walk(coords)
    if not points:
        return None, None
    return sum(p[1] for p in points) / len(points), sum(p[0] for p in points) / len(points)


def _upsert(session: Session, payload: Dict[str, Any]) -> bool:
    existing = session.exec(
        select(InfrastructureFeature)
        .where(InfrastructureFeature.tenant_id == payload["tenant_id"])
        .where(InfrastructureFeature.source_system == payload["source_system"])
        .where(InfrastructureFeature.source_id == payload["source_id"])
    ).first()
    if existing:
        for key in ("category", "subtype", "name", "geometry_type", "geometry", "centroid_latitude", "centroid_longitude", "criticality_score", "vulnerability_score", "source_url", "properties"):
            setattr(existing, key, payload[key])
        existing.updated_at = datetime.now(timezone.utc)
        session.add(existing)
        return False
    session.add(InfrastructureFeature(**payload))
    return True


async def _directory_links(client: httpx.AsyncClient, url: str) -> List[str]:
    response = await client.get(url, headers={"User-Agent": "SitRep/3.0 CanadaRailImporter"})
    response.raise_for_status()
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', response.text, flags=re.I)
    return [urljoin(url, href) for href in hrefs if href not in ("../", "./")]


def _url_matches_code(url: str, code: str) -> bool:
    name = PurePosixPath(urlparse(url).path).name.lower()
    return bool(re.search(rf"(^|[_\-.]){re.escape(code.lower())}([_\-.]|$)", name))


async def _find_package(jurisdiction: str) -> str:
    code = jurisdiction.upper()
    if code not in JURISDICTIONS:
        raise ValueError(f"Unsupported jurisdiction: {jurisdiction}")
    if code not in RAIL_JURISDICTIONS:
        raise ValueError(f"No published NRWN rail package is expected for {code}")
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True) as client:
            root = await _directory_links(client, NRWN_DIRECTORY)
            candidates = [u for u in root if _url_matches_code(u, code) and (u.lower().endswith('.zip') or u.lower().endswith('/'))]
            expanded = list(candidates)
            for url in candidates:
                if url.endswith('/'):
                    try:
                        expanded.extend(await _directory_links(client, url))
                    except httpx.HTTPError:
                        continue
            packages = [u for u in expanded if u.lower().endswith('.zip') and _url_matches_code(u, code)]
            packages.sort(key=lambda u: (0 if ('kml' in u.lower() or 'kmz' in u.lower()) else 1, -len(u)))
            if not packages:
                raise CanadaRailImportError(f"No NRWN package found for {code}")
            return packages[0]
    except httpx.HTTPError as exc:
        raise CanadaRailImportError(str(exc)) from exc


async def _download_package(url: str) -> bytes:
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "SitRep/3.0 CanadaRailImporter"})
            response.raise_for_status()
            return response.content
    except httpx.HTTPError as exc:
        raise CanadaRailImportError(str(exc)) from exc


def _kml_lines(raw_zip: bytes, limit: int) -> List[Dict[str, Any]]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw_zip))
    except zipfile.BadZipFile as exc:
        raise CanadaRailImportError("NRWN package was not a valid ZIP archive") from exc
    names = [n for n in zf.namelist() if n.lower().endswith(('.kml', '.kmz'))]
    features: List[Dict[str, Any]] = []
    ns = {'k': 'http://www.opengis.net/kml/2.2'}
    for name in names:
        data = zf.read(name)
        if name.lower().endswith('.kmz'):
            try:
                nested = zipfile.ZipFile(io.BytesIO(data))
                kml_names = [n for n in nested.namelist() if n.lower().endswith('.kml')]
                if not kml_names:
                    continue
                data = nested.read(kml_names[0])
            except zipfile.BadZipFile:
                continue
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            continue
        placemarks = root.findall('.//k:Placemark', ns)
        if not placemarks:
            placemarks = root.findall('.//Placemark')
        for idx, pm in enumerate(placemarks):
            coords_el = pm.find('.//k:LineString/k:coordinates', ns)
            if coords_el is None:
                coords_el = pm.find('.//LineString/coordinates')
            if coords_el is None or not coords_el.text:
                continue
            coords = []
            for token in coords_el.text.split():
                parts = token.split(',')
                if len(parts) >= 2:
                    try:
                        coords.append([float(parts[0]), float(parts[1])])
                    except ValueError:
                        pass
            if len(coords) < 2:
                continue
            name_el = pm.find('k:name', ns)
            if name_el is None:
                name_el = pm.find('name')
            features.append({'name': name_el.text.strip() if name_el is not None and name_el.text else 'Railway track', 'geometry': {'type': 'LineString', 'coordinates': coords}, 'index': idx})
            if len(features) >= limit:
                return features
    return features


async def import_nrwn_rail(session: Session, jurisdiction: str, tenant_id: str = "default", limit: int = 5000) -> Dict[str, Any]:
    code = jurisdiction.upper()
    package_url = await _find_package(code)
    raw = await _download_package(package_url)
    features = _kml_lines(raw, max(1, min(limit, 5000)))
    created = updated = 0
    for idx, feature in enumerate(features):
        geometry = feature['geometry']
        lat, lon = _centroid(geometry)
        payload = {'tenant_id': tenant_id, 'category': 'transport', 'subtype': 'railway', 'name': feature['name'], 'geometry_type': geometry['type'], 'geometry': geometry, 'centroid_latitude': lat, 'centroid_longitude': lon, 'criticality_score': 0.78, 'vulnerability_score': 0.50, 'source_system': 'NRCan-NRWN', 'source_id': f'NRWN:{code}:{idx}', 'source_url': package_url, 'properties': {'jurisdiction': code, 'source': 'National Railway Network - GeoBase Series'}}
        was_created = _upsert(session, payload)
        created += int(was_created); updated += int(not was_created)
    session.commit()
    return {'source': 'NRCan National Railway Network', 'jurisdiction': code, 'package_url': package_url, 'created': created, 'updated': updated, 'fetched': len(features)}
