"""Agent API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth_deps import require_operational_read_access
from app.schemas import AgentDetailResponse, AgentListResponse, PaginationParams
from app.services import AgentService

router = APIRouter(prefix="/agents", tags=["agents"], dependencies=[Depends(require_operational_read_access)])


def get_agent_service(db: Session = Depends(get_db)) -> AgentService:
    """Dependency to get AgentService instance."""
    return AgentService(db)


@router.get("", response_model=AgentListResponse)
async def list_agents(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: str | None = Query(None, description="Filter by agent status"),
    service: AgentService = Depends(get_agent_service),
) -> AgentListResponse:
    """Get paginated list of agents with optional status filter."""
    params = PaginationParams(page=page, page_size=page_size)
    return service.get_agents(params, status)


@router.get("/{agent_id}", response_model=AgentDetailResponse)
async def get_agent(
    agent_id: int,
    service: AgentService = Depends(get_agent_service),
) -> AgentDetailResponse:
    """Get detailed agent information with transaction summary."""
    agent = service.get_agent_detail(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent
