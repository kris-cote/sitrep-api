from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def source_fingerprint(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def latest_source_fingerprint(
    db: AsyncSession,
    *,
    source_system: str,
    feature_id: str,
    tenant_id: str,
) -> Optional[str]:
    query = text("""
        SELECT features->>'source_fingerprint' AS fingerprint
        FROM observations
        WHERE source_system = :source_system
          AND tenant_id = :tenant_id
          AND features->>'feature_id' = :feature_id
        ORDER BY collected_at DESC
        LIMIT 1
    """)
    result = await db.execute(
        query,
        {
            "source_system": source_system,
            "feature_id": feature_id,
            "tenant_id": tenant_id,
        },
    )
    row = result.fetchone()
    return str(row[0]) if row and row[0] else None


async def classify_feed_change(db: AsyncSession, observation: Dict[str, Any]) -> Dict[str, Any]:
    features = observation.setdefault("features", {})
    feature_id = str(features.get("feature_id") or "")
    source_system = str(observation.get("source_system") or "unknown")
    tenant_id = str(observation.get("tenant_id") or "default")
    fingerprint = source_fingerprint(observation.get("raw_payload") or observation)
    features["source_fingerprint"] = fingerprint

    if not feature_id:
        return {"is_new": True, "is_changed": True, "fingerprint": fingerprint, "previous_fingerprint": None}

    previous = await latest_source_fingerprint(
        db,
        source_system=source_system,
        feature_id=feature_id,
        tenant_id=tenant_id,
    )
    return {
        "is_new": previous is None,
        "is_changed": previous != fingerprint,
        "fingerprint": fingerprint,
        "previous_fingerprint": previous,
    }
