"""Transaction API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth_deps import require_operational_read_access
from app.schemas import TransactionDetailResponse, TransactionListResponse, PaginationParams
from app.services import TransactionService

router = APIRouter(prefix="/transactions", tags=["transactions"], dependencies=[Depends(require_operational_read_access)])


def get_transaction_service(db: Session = Depends(get_db)) -> TransactionService:
    """Dependency to get TransactionService instance."""
    return TransactionService(db)


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    agent_id: int | None = Query(None, description="Filter by agent ID"),
    status: str | None = Query(None, description="Filter by transaction status"),
    min_risk: int | None = Query(None, ge=0, le=100, description="Minimum risk score"),
    max_risk: int | None = Query(None, ge=0, le=100, description="Maximum risk score"),
    service: TransactionService = Depends(get_transaction_service),
) -> TransactionListResponse:
    """Get paginated transactions with optional filters."""
    params = PaginationParams(page=page, page_size=page_size)
    return service.get_transactions(params, agent_id, status, min_risk, max_risk)


@router.get("/{transaction_id}", response_model=TransactionDetailResponse)
async def get_transaction(
    transaction_id: int,
    service: TransactionService = Depends(get_transaction_service),
) -> TransactionDetailResponse:
    """Get detailed transaction with agent info and security events."""
    transaction = service.get_transaction_detail(transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction
