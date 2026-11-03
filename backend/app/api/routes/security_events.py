"""Security Events API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth_deps import require_operational_read_access
from app.schemas import PaginationParams, PaginatedResponse, SecurityEventResponse
from app.services import SecurityEventService

router = APIRouter(prefix="/security-events", tags=["security-events"], dependencies=[Depends(require_operational_read_access)])


def get_security_event_service(db: Session = Depends(get_db)) -> SecurityEventService:
    """Dependency to get SecurityEventService instance."""
    return SecurityEventService(db)


@router.get("", response_model=PaginatedResponse[SecurityEventResponse])
async def list_security_events(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    agent_id: int | None = Query(None, description="Filter by agent ID"),
    transaction_id: int | None = Query(None, description="Filter by transaction ID"),
    event_type: str | None = Query(None, description="Filter by event type"),
    severity: str | None = Query(None, description="Filter by severity"),
    service: SecurityEventService = Depends(get_security_event_service),
) -> PaginatedResponse[SecurityEventResponse]:
    """Get paginated security events with optional filters."""
    params = PaginationParams(page=page, page_size=page_size)
    return service.get_security_events(params, agent_id, transaction_id, event_type, severity)
