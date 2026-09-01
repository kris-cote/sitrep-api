from sqlmodel import Session, SQLModel, create_engine

from app.models.dependency import DependencyEdge
from app.models.infrastructure import InfrastructureFeature
from app.models.situation import SituationRecord
from app.services.canada_infrastructure_import import NRN_MAJOR_ROAD_LAYERS, normalize_nrn_major_road
from app.services.situation_impact import analyze_situation_infrastructure_impact


def test_nrn_major_road_layers_cover_all_provinces_and_territories():
    assert set(NRN_MAJOR_ROAD_LAYERS) == {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}


def test_normalize_nrn_major_road_preserves_jurisdiction():
    feature = {
        "id": "road-1",
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [[-123.0, 49.0], [-123.1, 49.1]]},
        "properties": {"ROUTENAME1": "Example Highway"},
    }
    item = normalize_nrn_major_road(feature, jurisdiction="BC", tenant_id="pilot")
    assert item is not None
    assert item["category"] == "transport"
    assert item["subtype"] == "road"
    assert item["properties"]["jurisdiction"] == "BC"
    assert item["source_system"] == "StatCan-NRN"


def test_situation_impact_uses_explicit_dependency_cascade():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        situation = SituationRecord(
            tenant_id="pilot",
            domain="wildfire-emergency",
            title="Test fire",
            latitude=49.0,
            longitude=-123.0,
            radius_km=25.0,
            risk_score=0.5,
            urgency_score=0.5,
        )
        road = InfrastructureFeature(
            tenant_id="pilot",
            category="transport",
            subtype="road",
            name="Evacuation Route",
            geometry_type="LineString",
            geometry={"type": "LineString", "coordinates": [[-123.01, 49.01], [-123.02, 49.02]]},
            centroid_latitude=49.015,
            centroid_longitude=-123.015,
            criticality_score=0.9,
            vulnerability_score=0.6,
        )
        hospital = InfrastructureFeature(
            tenant_id="pilot",
            category="health",
            subtype="hospital",
            name="Hospital access",
            geometry_type="Point",
            geometry={"type": "Point", "coordinates": [-123.03, 49.03]},
            centroid_latitude=49.03,
            centroid_longitude=-123.03,
        )
        session.add(situation)
        session.add(road)
        session.add(hospital)
        session.commit()
        session.refresh(situation)
        session.refresh(road)
        session.refresh(hospital)
        session.add(DependencyEdge(
            tenant_id="pilot",
            upstream_type="infrastructure",
            upstream_id=road.id,
            downstream_type="infrastructure",
            downstream_id=hospital.id,
            relationship="access_route",
            confidence=1.0,
            criticality=0.9,
        ))
        session.commit()

        result = analyze_situation_infrastructure_impact(session, situation.id, radius_km=25.0)
        assert result["direct_impacts"]
        assert any(item["downstream_id"] == hospital.id for item in result["cascade_impacts"])
        assert result["risk_score"] >= 0.5
