from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/readiness", tags=["readiness"])


@router.get("/challenge-alignment")
async def read_challenge_alignment():
    return {
        "status": "ok",
        "challenge": {
            "name": "Multi-modal AI for Advanced Situational Decisions",
            "prototype_name": "SitRep / Space Hub - The Veil",
            "trl_positioning": "TRL 4 prototype with Component 1b maturation path toward TRL 5",
        },
        "essential_outcome": {
            "requirement": (
                "Deliver an AI model that can aggregate, ingest, fuse, and generate outputs "
                "from at least two heterogeneous data types to produce output metrics and measures."
            ),
            "status": "met_at_prototype_level",
            "evidence": [
                "Live API ingests and fuses more than two heterogeneous data types.",
                "Scenario A demonstrates radar, EO/video, RF detection, and text report fusion.",
                "Scenario B demonstrates satellite, RF detection, telemetry, and text report fusion.",
                "Scenario C demonstrates radar, EO/IR, telemetry, and text report fusion.",
                "Fusion outputs include association score, learned model score, final confidence, uncertainty score, and operator-facing explanation.",
            ],
        },
        "desired_outcomes": {
            "advanced_ai_spatiotemporal_uncertainty": {
                "status": "partially_met_with_clear_maturation_path",
                "current_capabilities": [
                    "trained local association model",
                    "baseline fusion model",
                    "spatiotemporal gating",
                    "estimated speed and distance checks",
                    "confidence scoring",
                    "uncertainty scoring",
                    "confidence and uncertainty drivers",
                ],
                "component_1b_maturation": [
                    "expand synthetic and representative training data",
                    "train multimodal temporal association model",
                    "calibrate uncertainty estimates",
                    "evaluate model performance against realistic ISR/C2 datasets",
                ],
            },
            "entity_resolution_dynamic_graph_tracking": {
                "status": "met_at_prototype_level",
                "current_capabilities": [
                    "entities table",
                    "observations table",
                    "tracks and track_points",
                    "associations",
                    "fusion_outputs",
                    "provenance_records",
                    "operator_actions",
                    "persistent object tracking across time and space",
                ],
            },
            "policy_aware_provenance_lineage": {
                "status": "met_at_prototype_level",
                "current_capabilities": [
                    "policy evaluator records classification_in and classification_out",
                    "release_decision captured",
                    "cross_domain_transfer field captured",
                    "redacted_fields captured",
                    "handling_caveats captured",
                    "derived_from_observations captured",
                    "processing_steps captured",
                    "source lineage preserved through provenance endpoint",
                ],
                "limitations": [
                    "Prototype does not perform real classified cross-domain downgrade.",
                    "Operational deployment would require DND/CAF security accreditation and policy integration.",
                ],
            },
            "scalable_real_time_fusion_explainability": {
                "status": "partially_met_with_clear_scale_path",
                "current_capabilities": [
                    "FastAPI ingestion and COP endpoints",
                    "Postgres-backed persistence",
                    "Dockerized local deployment",
                    "Cloudflare tunnel public demo path",
                    "Base44 operator console integration",
                    "explainable fusion outputs",
                    "operator review records",
                ],
                "component_1b_maturation": [
                    "add asynchronous queue/worker processing",
                    "stream observations through Redis or event bus",
                    "add load/latency testing",
                    "add operational logging and monitoring dashboards",
                ],
            },
            "swap_edge_constraints": {
                "status": "partially_met_with_edge_ready_prototype_elements",
                "current_capabilities": [
                    "local model runtime",
                    "no cloud AI required for core fusion",
                    "small joblib model artifact",
                    "Dockerized deployment",
                    "fallback deterministic scoring if model unavailable",
                ],
                "component_1b_maturation": [
                    "benchmark CPU/RAM/storage usage",
                    "produce edge deployment profile",
                    "evaluate mini-PC / ruggedized local deployment",
                    "export or repackage model for lightweight runtime such as ONNX where appropriate",
                ],
            },
        },
        "demonstrated_scenarios": [
            {
                "id": "scenario_a",
                "name": "Maritime ISR Vessel Track",
                "endpoint": "POST /api/v1/demo/vessel-track",
                "tenant": "proposal_demo_001",
                "modalities": ["radar", "eo_video", "rf_detection", "text_report"],
                "object_type": "vessel",
                "brief_mapping": "Maritime Task Group Operations / multi-domain ISR fusion",
            },
            {
                "id": "scenario_b",
                "name": "Arctic ISR Fusion",
                "endpoint": "POST /api/v1/demo/arctic-isr",
                "tenant": "arctic_demo",
                "modalities": ["satellite", "rf_detection", "telemetry", "text_report"],
                "object_type": "vessel",
                "brief_mapping": "Joint ISR Fusion for Arctic Operations",
            },
            {
                "id": "scenario_c",
                "name": "Airborne Multi-Sensor Track",
                "endpoint": "POST /api/v1/demo/airborne-track",
                "tenant": "airborne_demo",
                "modalities": ["radar", "eo_ir", "telemetry", "text_report"],
                "object_type": "aircraft",
                "brief_mapping": "Airborne Multi-Sensor Platforms",
            },
            {
                "id": "adversarial",
                "name": "Impossible-Movement Rejection",
                "endpoint": "POST /api/v1/demo/adversarial-track",
                "tenant": "adversarial_demo",
                "modalities": ["radar", "eo_video", "rf_detection"],
                "object_type": "vessel",
                "brief_mapping": "Operator trust, uncertainty, and physically plausible fusion",
            },
        ],
        "operator_trust_features": [
            "fusion_explanation",
            "confidence_drivers",
            "uncertainty_drivers",
            "spatiotemporal gate_reason",
            "rejected_candidate_evidence in adversarial scenario",
            "operator_actions audit trail",
            "provenance processing_steps",
        ],
        "recommended_proposal_claim": (
            "SitRep is a TRL 4 AI-enabled multi-modal fusion prototype that demonstrates "
            "heterogeneous ingestion, learned association scoring, persistent entity tracking, "
            "spatiotemporal gating, uncertainty scoring, policy-aware provenance, and "
            "human-in-the-loop operator review across maritime, Arctic ISR, and airborne scenarios."
        ),
        "important_non_claims": [
            "The prototype is not claimed as an operational CAF-certified system.",
            "The current trained model is based on synthetic data and requires validation on representative datasets.",
            "The prototype does not perform real classified cross-domain downgrade.",
            "The prototype does not support autonomous targeting or weapons-release decisions.",
        ],
    }
@router.get("/edge-profile")
async def read_edge_profile():
    return {
        "status": "ok",
        "profile_name": "SitRep Edge/SWaP Prototype Profile",
        "deployment_mode": "local_containerized_edge_prototype",
        "core_runtime": {
            "api": "FastAPI/Uvicorn",
            "database": "Postgres",
            "model_runtime": "scikit-learn/joblib",
            "containerized": True,
            "requires_cloud_ai_for_core_fusion": False,
            "offline_core_fusion_possible": True,
        },
        "model_profile": {
            "association_model": "sitrep_association_model_v1",
            "model_type": "random_forest_association_classifier",
            "artifact": "app/services/ai/models/sitrep_association_model.joblib",
            "approx_model_size_kb": 142.13,
            "fallback_mode": "deterministic_fallback_scoring",
            "fallback_available_if_model_missing": True,
        },
        "swap_considerations": {
            "size": "Containerized software stack suitable for laptop/mini-PC prototype deployment.",
            "weight": "No specialized hardware required for current TRL 4 prototype.",
            "power": "Expected to run on conventional laptop or small-form-factor edge compute; formal power benchmarking remains Component 1b work.",
            "network": "Core fusion can run locally; public demo path uses Cloudflare tunnel but is not required for edge operation.",
        },
        "current_edge_evidence": [
            "API and model run locally on developer laptop.",
            "Core fusion does not require OpenAI or external cloud model calls.",
            "Trained model artifact is small enough for tactical-edge prototype use.",
            "Deterministic fallback scoring exists if the trained model artifact is unavailable.",
            "Dockerized deployment supports repeatable local installation.",
        ],
        "component_1b_edge_maturation_plan": [
            "Measure CPU, RAM, disk, and latency under synthetic observation load.",
            "Benchmark model scoring latency and end-to-end ingestion-to-COP latency.",
            "Test deployment on mini-PC / ruggedized edge compute.",
            "Evaluate offline operation and delayed synchronization.",
            "Package model for lightweight runtime such as ONNX if appropriate.",
            "Document SWaP envelope for target tactical-edge deployment profiles.",
        ],
        "current_limitations": [
            "No formal CPU/RAM/power benchmark has been completed yet.",
            "No ruggedized field hardware test has been completed yet.",
            "No formal disconnected/offline synchronization test has been completed yet.",
            "Current public demo depends on Cloudflare tunnel, but core fusion does not.",
        ],
        "readiness_summary": (
            "SitRep currently demonstrates edge-ready prototype elements: local model runtime, "
            "small model artifact, Dockerized deployment, no cloud AI dependency for core fusion, "
            "and deterministic fallback scoring. Component 1b will formalize SWaP testing and "
            "edge deployment validation."
        ),
    }
