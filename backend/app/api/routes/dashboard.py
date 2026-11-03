"""Dashboard API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth_deps import require_operational_read_access
from app.schemas import DashboardSummary
from app.services import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(require_operational_read_access)])


def get_dashboard_service(db: Session = Depends(get_db)) -> DashboardService:
    """Dependency to get DashboardService instance."""
    return DashboardService(db)


@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardSummary:
    """Get dashboard KPI summary."""
    return service.get_summary()
