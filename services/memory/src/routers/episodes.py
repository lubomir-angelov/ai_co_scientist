from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime
from typing import Any, Dict, Optional

from ..graph_client import get_graphiti

router = APIRouter(tags=["episodes"])

class EpisodeIn(BaseModel):
    project_id: str
    session_id: str
    run_id: str
    step_id: str
    episode_type: str
    tool_used: Optional[str] = None
    inputs: Dict[str, Any]
    result: Dict[str, Any]
    timestamp: datetime

class EpisodeOut(BaseModel):
    episode_id: str
    status: str = "ok"


@router.post("/episodes", response_model=EpisodeOut)
async def create_episode(ep: EpisodeIn):
    graphiti = get_graphiti()

    # PSEUDO-CODE – adapt to actual Graphiti episode API:
    # you will likely use a Pydantic model from graphiti_core like EpisodeCreate
    episode_payload = {
        "project_id": ep.project_id,
        "session_id": ep.session_id,
        "run_id": ep.run_id,
        "step_id": ep.step_id,
        "episode_type": ep.episode_type,
        "content": {
            "tool_used": ep.tool_used,
            "inputs": ep.inputs,
            "result": ep.result,
        },
        "timestamp": ep.timestamp.isoformat(),
    }

    episode = await graphiti.add_episodes([episode_payload])
    # assume add_episodes returns a list; adjust as needed

    return EpisodeOut(episode_id=str(episode[0].id))
