from app.services.ai_orchestration import classify_intent
from app.services.ai_provenance import _fingerprint


def test_ai_orchestrator_routes_deterministic_questions():
    assert classify_intent("What resources are available for this incident?") == "resources"
    assert classify_intent("What is the 6 hour forecast and should we pre-stage?") == "forecast"


def test_ai_orchestrator_routes_analysis_and_planning_questions():
    assert classify_intent("What changed and what concerns you most?") == "situation"
    assert classify_intent("What should we do? Give me course of action options") == "coa"
    assert classify_intent("Assume Highway 19 closes and compare scenarios") == "scenario"
    assert classify_intent("Red team this plan and find failure modes") == "red-team"


def test_ai_provenance_fingerprint_is_stable_and_sensitive():
    a = _fingerprint({"question": "What changed?", "situation_id": "abc"})
    b = _fingerprint({"situation_id": "abc", "question": "What changed?"})
    c = _fingerprint({"question": "What changed?", "situation_id": "xyz"})
    assert a == b
    assert a != c
    assert len(a) == 64
