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
from prometheus_fastapi_instrumentator import Instrumentator
from app.routes import compliance

app = FastAPI(
    title="SitRep Decision Intelligence API",
    version="2.7.0",
    description="Unified situational awareness, cross-source correlation, population and wildfire exposure screening, Canadian infrastructure context, mission packs and human-authorized decision intelligence",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.on_event("startup")
def on_startup():
    init_db()


app.include_router(core.router)
app.include_router(tenants.router)
app.include_router(missions.router)
app.include_router(events.router)
app.include_router(commands.router)
app.include_router(agents.router)
app.include_router(integrations.router)
app.include_router(observations_router)
app.include_router(entities_router)
app.include_router(cop_router)
app.include_router(demo_router)
app.include_router(provenance_router)
app.include_router(model_router)
app.include_router(decisions_router)
app.include_router(mission_packs_router)
app.include_router(canadian_connectors_router)
app.include_router(canadian_exposures_router)
app.include_router(situations_router)
app.include_router(exposures_router)
app.include_router(infrastructure_router)
app.include_router(satellite_router, prefix="/api/v1/satellite", tags=["satellite"])
app.include_router(readiness_router, prefix="/api/v1/readiness", tags=["readiness"])
app.include_router(challenge_alignment_router)
app.include_router(compliance.router)
