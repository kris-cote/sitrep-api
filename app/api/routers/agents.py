# app/api/routers/agents.py
from fastapi import APIRouter, Depends
from app.models.schemas import AgentRunRequest, AgentRunResponse
from app.core.security import verify_api_key

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.post("/{agent_name}/run", response_model=AgentRunResponse)
def run_agent(
    agent_name: str,
    payload: AgentRunRequest,
    _: str = Depends(verify_api_key),
):
    # For TRL-4: just echo and mark accepted
    return AgentRunResponse(
        agent=agent_name,
        status="accepted",
        result={
            "message": "Agent execution stubbed (TRL-4). Input received.",
            "input": payload.model_dump(),
        },
    )
