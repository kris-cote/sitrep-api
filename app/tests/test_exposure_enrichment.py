from datetime import datetime, timezone

from sqlmodel import Session, SQLModel, create_engine

from app.models.exposure import ExposureAsset
from app.models.situation import SituationRecord
from app.services.exposure_enrichment import enrich_situation_exposure


def test_nearby_critical_asset_increases_situation_risk():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        situation = SituationRecord(
            tenant_id="pilot",
            domain="wildfire-emergency",
            title="Wildfire situation",
            latitude=49.20,
            longitude=-123.90,
            radius_km=50.0,
            confidence=0.8,
            risk_score=0.45,
            urgency_score=0.50,
            last_observed_at=datetime.now(timezone.utc),
        )
        near_hospital = ExposureAsset(
            tenant_id="pilot",
            asset_type="hospital",
            name="Regional Hospital",
            latitude=49.22,
            longitude=-123.91,
            criticality_score=1.0,
            vulnerability_score=0.8,
            population=500,
        )
        far_asset = ExposureAsset(
            tenant_id="pilot",
            asset_type="substation",
            name="Distant Substation",
            latitude=50.50,
            longitude=-125.50,
            criticality_score=1.0,
            vulnerability_score=1.0,
        )
        session.add(situation)
        session.add(near_hospital)
        session.add(far_asset)
        session.commit()
        session.refresh(situation)

        result = enrich_situation_exposure(session, situation.id, radius_km=50.0)

        assert result["asset_count"] == 1
        assert result["population_exposed"] == 500
        assert result["assets"][0]["name"] == "Regional Hospital"
        assert result["risk_score"] > 0.45
        assert result["severity"] in {"medium", "high", "critical"}
