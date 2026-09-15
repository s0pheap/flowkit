"""Flow Project Pool API - Manage pre-created Flow projects for user assignment."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

from agent import auth
from agent.db import crud

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flow-pool", tags=["flow-pool"])


class FlowProjectPoolItem(BaseModel):
    flow_project_id: str
    assigned_to_user: Optional[str]
    assigned_at: Optional[str]
    notes: Optional[str]
    created_at: str


class AddFlowProjectRequest(BaseModel):
    flow_project_id: str
    notes: Optional[str] = None


@router.get("", response_model=list[FlowProjectPoolItem])
async def list_pool(assigned: Optional[bool] = Query(None, description="Filter: true=assigned only, false=available only, null=all")):
    """List all Flow projects in the pool. Admin only."""
    auth.require_admin()
    projects = await crud.list_flow_project_pool(assigned_only=assigned)
    return projects


@router.post("", response_model=FlowProjectPoolItem)
async def add_to_pool(body: AddFlowProjectRequest):
    """Add a Flow project UUID to the pool. Admin only.

    The Flow project must be created manually in the Flow UI first.
    This just registers it in the pool for assignment to users.
    """
    auth.require_admin()

    # Check if already in pool
    existing = await crud.get_flow_project_from_pool(body.flow_project_id)
    if existing:
        raise HTTPException(409, f"Flow project {body.flow_project_id} already in pool")

    project = await crud.add_flow_project_to_pool(body.flow_project_id, body.notes)
    logger.info("Added Flow project %s to pool", body.flow_project_id)
    return project


@router.get("/{flow_project_id}", response_model=FlowProjectPoolItem)
async def get_pool_project(flow_project_id: str):
    """Get details of a Flow project in the pool. Admin only."""
    auth.require_admin()
    project = await crud.get_flow_project_from_pool(flow_project_id)
    if not project:
        raise HTTPException(404, "Flow project not found in pool")
    return project


@router.delete("/{flow_project_id}")
async def remove_from_pool(flow_project_id: str):
    """Remove a Flow project from the pool. Admin only.

    This does NOT delete the project in Flow, just removes it from the pool.
    If already assigned, the user keeps access via user_project table.
    """
    auth.require_admin()
    success = await crud.remove_flow_project_from_pool(flow_project_id)
    if not success:
        raise HTTPException(404, "Flow project not found in pool")
    logger.info("Removed Flow project %s from pool", flow_project_id)
    return {"ok": True}


@router.post("/{flow_project_id}/assign")
async def assign_to_user(flow_project_id: str, user_id: str = Body(..., embed=True)):
    """Manually assign a Flow project to a user. Admin only."""
    auth.require_admin()

    pool_project = await crud.get_flow_project_from_pool(flow_project_id)
    if not pool_project:
        raise HTTPException(404, "Flow project not found in pool")

    if pool_project.get("assigned_to_user"):
        raise HTTPException(409, f"Flow project already assigned to user {pool_project['assigned_to_user']}")

    user = await crud.get_api_user(user_id)
    if not user:
        raise HTTPException(404, f"User {user_id} not found")

    result = await crud.assign_flow_project_to_user(flow_project_id, user_id)
    logger.info("Assigned Flow project %s to user %s", flow_project_id, user_id)
    return result


@router.post("/{flow_project_id}/unassign")
async def unassign(flow_project_id: str):
    """Unassign a Flow project, making it available again. Admin only.

    The user's access in user_project remains (they can still use the project),
    but the pool marks it as available for assignment to someone else.
    """
    auth.require_admin()

    pool_project = await crud.get_flow_project_from_pool(flow_project_id)
    if not pool_project:
        raise HTTPException(404, "Flow project not found in pool")

    if not pool_project.get("assigned_to_user"):
        raise HTTPException(400, "Flow project is not assigned")

    result = await crud.unassign_flow_project(flow_project_id)
    logger.info("Unassigned Flow project %s", flow_project_id)
    return result


@router.get("/available/next", response_model=Optional[FlowProjectPoolItem])
async def get_next_available():
    """Get the next available (unassigned) Flow project from the pool. Admin only."""
    auth.require_admin()
    project = await crud.get_available_flow_project_from_pool()
    return project


@router.get("/user/{user_id}/projects", response_model=list[FlowProjectPoolItem])
async def get_user_projects(user_id: str):
    """Get all Flow projects assigned to a user from the pool. Admin only."""
    auth.require_admin()
    projects = await crud.get_user_flow_projects_from_pool(user_id)
    return projects
