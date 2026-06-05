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
# Optional: if you are exposing /metrics via prometheus_fastapi_instrumentator
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(
    title="Situational Awareness API",
    version="1.0.0",
    description="Unified mission automation and awareness",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
# IMPORTANT: instrument BEFORE startup completes (or you'll hit "Cannot add middleware after an application has started")
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

@app.on_event("startup")
def on_startup():
    init_db()

# Routers
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
app.include_router(satellite_router, prefix="/api/v1/satellite", tags=["satellite"])
app.include_router(readiness_router, prefix="/api/v1/readiness", tags=["readiness"])
app.include_router(readiness_router, prefix="/api/v1/readiness", tags=["readiness"])
app.include_router(challenge_alignment_router)
