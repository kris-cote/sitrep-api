from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.models.db import init_db
from app.api.routers import core, tenants, missions, events, commands, agents, integrations
from app.routers.satellite_proxy import router as satellite_router
from app.api.routers.readiness import router as readiness_router
from app.routes.observations import router as observations_router
from app.routes.cop import router as cop_router
from app.routes.demo import router as demo_router
from app.routes.entities import router as entities_router
from app.routes.model import router as model_router
from app.routes.challenge_alignment import router as challenge_alignment_router
from app.routes.provenance import router as provenance_router
from app.routes.decisions import router as decisions_router
from app.routes.mission_packs import router as mission_packs_router
from app.routes.canadian_connectors import router as canadian_connectors_router
from app.routes.canadian_exposures import router as canadian_exposures_router
from app.routes.situations import router as situations_router
from app.routes.exposures import router as exposures_router
from app.routes.infrastructure import router as infrastructure_router
from app.routes.dependencies import router as dependencies_router
from app.routes.emergency_infrastructure import router as emergency_infrastructure_router
from prometheus_fastapi_instrumentator import Instrumentator
from app.routes import compliance

app=FastAPI(title="SitRep Decision Intelligence API",version="3.4.0",description="Canada-wide decision intelligence with national roads, rail, communities, healthcare and population enrichment; provincial utility adapters; emergency-response infrastructure including Ontario AFFES and Quebec fire stations; cross-source correlation, infrastructure-impact and dependency-cascade analysis; mission packs and human authorization.")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=False,allow_methods=["*"],allow_headers=["*"])
Instrumentator().instrument(app).expose(app,endpoint="/metrics",include_in_schema=False)
@app.on_event("startup")
def on_startup(): init_db()
for r in [core.router,tenants.router,missions.router,events.router,commands.router,agents.router,integrations.router,observations_router,entities_router,cop_router,demo_router,provenance_router,model_router,decisions_router,mission_packs_router,canadian_connectors_router,canadian_exposures_router,situations_router,exposures_router,infrastructure_router,dependencies_router,emergency_infrastructure_router]: app.include_router(r)
app.include_router(satellite_router,prefix="/api/v1/satellite",tags=["satellite"])
app.include_router(readiness_router,prefix="/api/v1/readiness",tags=["readiness"])
app.include_router(challenge_alignment_router)
app.include_router(compliance.router)
