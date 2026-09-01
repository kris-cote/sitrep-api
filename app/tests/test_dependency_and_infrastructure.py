from sqlmodel import Session, SQLModel, create_engine

from app.models.dependency import DependencyEdge
from app.services.bc_infrastructure_import import normalize_bc_infrastructure
from app.services.dependency_graph import analyze_dependency_cascade


def test_transmission_import_redacts_voltage():
    feature = {
        "id": 77,
        "geometry": {"type": "LineString", "coordinates": [[-124.0, 49.0], [-123.8, 49.2]]},
        "properties": {"OBJECTID": 77, "CIRCUIT_NAME": "Public Line", "OWNER": "Utility", "VOLTAGE": 500},
    }
    payload = normalize_bc_infrastructure("transmission", feature, tenant_id="pilot")
    assert payload is not None
    assert payload["subtype"] == "transmission_line"
    assert "VOLTAGE" not in payload["properties"]["attributes"]
    assert payload["source_system"] == "BC-DataBC-ArcGIS"


def test_dependency_cascade_propagates_multiple_hops():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine, tables=[DependencyEdge.__table__])
    with Session(engine) as session:
        session.add(DependencyEdge(
            tenant_id="pilot",
            upstream_type="infrastructure",
            upstream_id="line-1",
            downstream_type="infrastructure",
            downstream_id="substation-1",
            relationship="supplies",
            confidence=1.0,
            criticality=0.9,
        ))
        session.add(DependencyEdge(
            tenant_id="pilot",
            upstream_type="infrastructure",
            upstream_id="substation-1",
            downstream_type="exposure",
            downstream_id="hospital-1",
            relationship="supplies",
            confidence=0.9,
            criticality=1.0,
        ))
        session.commit()

        result = analyze_dependency_cascade(session, "pilot", "infrastructure", "line-1", max_depth=4)

    assert result["affected_nodes"] == 2
    assert len(result["impact_paths"]) == 2
    hospital = next(item for item in result["impact_paths"] if item["downstream_id"] == "hospital-1")
    assert hospital["depth"] == 2
    assert hospital["propagated_impact_score"] > 0.7
