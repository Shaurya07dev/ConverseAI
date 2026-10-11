"""
VaakSetu Backend — Agent CRUD Routes

Endpoints:
  POST   /api/agents       — Create a new agent
  GET    /api/agents        — List the caller's agents
  GET    /api/agents/{id}   — Get single agent
  PUT    /api/agents/{id}   — Update agent
  DELETE /api/agents/{id}   — Delete agent
"""

import uuid
import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Optional

from backend.database import (
    create_agent,
    get_agent,
    list_agents,
    update_agent,
    delete_agent,
)
from backend.auth import current_user, owned

logger = logging.getLogger("vaaksetu.routes.agents")
router = APIRouter(prefix="/api/agents", tags=["agents"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Request / Response Models
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AgentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    domain: str = Field(min_length=1)
    customDomain: Optional[str] = ""
    inputs: list[str] = ["Voice"]
    fields: list[str] = []
    prompt: Optional[str] = ""
    greeting: Optional[str] = ""
    triggers: list[str] = []
    escalation: dict = {}
    escalation_message: Optional[str] = ""
    default_language: Optional[str] = "hi-IN"


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    customDomain: Optional[str] = None
    inputs: Optional[list[str]] = None
    fields: Optional[list[str]] = None
    prompt: Optional[str] = None
    greeting: Optional[str] = None
    triggers: Optional[list[str]] = None
    escalation: Optional[dict] = None
    escalation_message: Optional[str] = None
    default_language: Optional[str] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Routes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("")
async def api_create_agent(req: AgentCreateRequest, user: str = Depends(current_user)):
    """Create a new agent from the frontend wizard form."""
    agent_id = str(uuid.uuid4())[:8]
    agent_data = req.model_dump()
    agent_data["id"] = agent_id
    agent_data["owner_id"] = user

    # Auto-generate greeting if not provided
    if not agent_data.get("greeting"):
        display_domain = agent_data.get("customDomain") or agent_data["domain"]
        agent_data["greeting"] = (
            f"Namaste! Main {agent_data['name']} hoon. "
            f"Aaj main aapki {display_domain} se related madad karunga. "
            f"Kya aap shuru karein?"
        )

    agent = await create_agent(agent_data)
    logger.info(f"Agent created: {agent_id} ({agent_data['name']})")
    return {"status": "ok", "agent": agent}


@router.get("")
async def api_list_agents(user: str = Depends(current_user)):
    """List all agents."""
    agents = await list_agents(user)
    return {"status": "ok", "agents": agents}


@router.get("/{agent_id}")
async def api_get_agent(agent_id: str, user: str = Depends(current_user)):
    """Get a single agent by ID."""
    agent = owned(await get_agent(agent_id), user, "Agent")
    return {"status": "ok", "agent": agent}


@router.put("/{agent_id}")
async def api_update_agent(agent_id: str, req: AgentUpdateRequest, user: str = Depends(current_user)):
    """Update an existing agent."""
    existing = owned(await get_agent(agent_id), user, "Agent")

    # Merge: only update fields that were provided
    update_data = existing.copy()
    for key, val in req.model_dump(exclude_none=True).items():
        update_data[key] = val

    agent = await update_agent(agent_id, update_data)
    logger.info(f"Agent updated: {agent_id}")
    return {"status": "ok", "agent": agent}


@router.delete("/{agent_id}")
async def api_delete_agent(agent_id: str, user: str = Depends(current_user)):
    """Delete an agent and all its sessions."""
    owned(await get_agent(agent_id), user, "Agent")
    await delete_agent(agent_id)
    logger.info(f"Agent deleted: {agent_id}")
    return {"status": "ok", "message": "Agent deleted"}
