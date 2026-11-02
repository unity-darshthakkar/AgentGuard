"""Business logic services for AgentGuard."""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    AgentStatus,
    SecurityEvent,
    SecurityEventType,
    Transaction,
    TransactionStatus,
    AgentCredential,
    SpendingPolicy,
    AuthorizationDecision,
    CredentialStatus,
    PolicyStatus,
)
from app.schemas import (
    AgentDetailResponse,
    AgentListResponse,
    AgentResponse,
    DashboardSummary,
    PaginationParams,
    PaginatedResponse,
    TransactionDetailResponse,
    TransactionListResponse,
    TransactionResponse,
    SecurityEventResponse,
    CredentialResponse,
    SpendingPolicyResponse,
    AuthorizationDecisionResponse,
    AuthorizationDecisionListResponse,
)
from app.services.auth import (
    register_agent_credential,
    get_active_credential,
    revoke_credential,
    check_credential_valid,
    create_spending_policy,
    get_active_policy,
    revoke_policy,
    create_nonce,
    consume_nonce,
    cleanup_expired_nonces,
    verify_signature,
    canonical_request_string,
    compute_body_hash,
    load_public_key,
    AuthorizationService,
    record_authorization_decision,
    check_idempotency,
    parse_policy_currencies,
    parse_policy_allowed_merchants,
    parse_policy_blocked_merchants,
    capture_reservation,
    release_reservation,
    expire_reservation,
    get_reservation_by_auth_decision,
    expire_old_reservations,
)
from app.services.paypal_orchestration import (
    orchestrate_paypal_order,
    get_paypal_order_binding,
    PayPalOrderBinding,
    PayPalOrchestrationError,
)


class AgentService:
    """Service for agent operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_agents(self, params: PaginationParams, status: Optional[str] = None) -> AgentListResponse:
        """Get paginated list of agents with optional status filter."""
        query = select(Agent)
        count_query = select(func.count(Agent.id))

        if status:
            query = query.where(Agent.status == status)
            count_query = count_query.where(Agent.status == status)

        total = self.db.execute(count_query).scalar_one()

        query = query.order_by(Agent.created_at.desc())
        query = query.offset((params.page - 1) * params.page_size).limit(params.page_size)

        agents = self.db.execute(query).scalars().all()
        items = [AgentResponse.model_validate(agent) for agent in agents]

        return AgentListResponse.create(items, total, params.page, params.page_size)

    def get_agent(self, agent_id: int) -> Optional[Agent]:
        """Get agent by ID."""
        return self.db.get(Agent, agent_id)

    def get_agent_by_agent_id(self, agent_id: str) -> Optional[Agent]:
        """Get agent by agent_id string."""
        return self.db.execute(select(Agent).where(Agent.agent_id == agent_id)).scalar_one_or_none()

    def get_agent_detail(self, agent_id: int) -> Optional[AgentDetailResponse]:
        """Get detailed agent info with transaction summary."""
        agent = self.get_agent(agent_id)
        if not agent:
            return None

        # Get transaction stats
        stats = self.db.execute(
            select(
                func.count(Transaction.id).label("total"),
                func.sum(
                    case((Transaction.status == TransactionStatus.APPROVED, 1), else_=0)
                ).label("approved"),
                func.sum(
                    case((Transaction.status == TransactionStatus.BLOCKED, 1), else_=0)
                ).label("blocked"),
                func.sum(
                    case((Transaction.status == TransactionStatus.UNDER_REVIEW, 1), else_=0)
                ).label("under_review"),
                func.coalesce(func.sum(Transaction.amount_usd), 0).label("volume"),
                func.coalesce(func.avg(Transaction.risk_score), 0).label("avg_risk"),
            ).where(Transaction.agent_id == agent_id)
        ).first()

        base = AgentResponse.model_validate(agent)
        return AgentDetailResponse(
            **base.model_dump(),
            transaction_count=stats.total or 0,
            approved_count=stats.approved or 0,
            blocked_count=stats.blocked or 0,
            under_review_count=stats.under_review or 0,
            total_volume_usd=float(stats.volume or 0),
            avg_risk_score=float(stats.avg_risk or 0),
        )


class TransactionService:
    """Service for transaction operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_transactions(
        self,
        params: PaginationParams,
        agent_id: Optional[int] = None,
        status: Optional[str] = None,
        min_risk: Optional[int] = None,
        max_risk: Optional[int] = None,
    ) -> TransactionListResponse:
        """Get paginated transactions with filters."""
        query = select(Transaction)
        count_query = select(func.count(Transaction.id))

        if agent_id:
            query = query.where(Transaction.agent_id == agent_id)
            count_query = count_query.where(Transaction.agent_id == agent_id)

        if status:
            query = query.where(Transaction.status == status)
            count_query = count_query.where(Transaction.status == status)

        if min_risk is not None:
            query = query.where(Transaction.risk_score >= min_risk)
            count_query = count_query.where(Transaction.risk_score >= min_risk)

        if max_risk is not None:
            query = query.where(Transaction.risk_score <= max_risk)
            count_query = count_query.where(Transaction.risk_score <= max_risk)

        total = self.db.execute(count_query).scalar_one()

        query = query.order_by(Transaction.requested_at.desc())
        query = query.offset((params.page - 1) * params.page_size).limit(params.page_size)

        transactions = self.db.execute(query).scalars().all()
        items = [TransactionResponse.model_validate(txn) for txn in transactions]

        return TransactionListResponse.create(items, total, params.page, params.page_size)

    def get_transaction(self, transaction_id: int) -> Optional[Transaction]:
        """Get transaction by ID."""
        return self.db.get(Transaction, transaction_id)

    def get_transaction_detail(self, transaction_id: int) -> Optional[TransactionDetailResponse]:
        """Get detailed transaction with agent and security events."""
        txn = self.get_transaction(transaction_id)
        if not txn:
            return None

        # Get agent
        agent = self.db.get(Agent, txn.agent_id)

        # Get security events
        events = self.db.execute(
            select(SecurityEvent).where(SecurityEvent.transaction_id == transaction_id)
        ).scalars().all()

        base = TransactionResponse.model_validate(txn)
        return TransactionDetailResponse(
            **base.model_dump(),
            agent=AgentResponse.model_validate(agent) if agent else None,
            security_events=[e for e in events],
        )


class DashboardService:
    """Service for dashboard KPI data."""

    def __init__(self, db: Session):
        self.db = db

    def get_summary(self) -> DashboardSummary:
        """Get dashboard summary KPIs."""
        # Agent counts
        total_agents = self.db.execute(select(func.count(Agent.id))).scalar_one()
        active_agents = self.db.execute(
            select(func.count(Agent.id)).where(Agent.status == AgentStatus.ACTIVE)
        ).scalar_one()
        suspended_agents = self.db.execute(
            select(func.count(Agent.id)).where(Agent.status == AgentStatus.SUSPENDED)
        ).scalar_one()
        pending_review_agents = self.db.execute(
            select(func.count(Agent.id)).where(Agent.status == AgentStatus.PENDING_REVIEW)
        ).scalar_one()

        # Transaction counts by status
        total_transactions = self.db.execute(select(func.count(Transaction.id))).scalar_one()
        approved_transactions = self.db.execute(
            select(func.count(Transaction.id)).where(Transaction.status == TransactionStatus.APPROVED)
        ).scalar_one()
        blocked_transactions = self.db.execute(
            select(func.count(Transaction.id)).where(Transaction.status == TransactionStatus.BLOCKED)
        ).scalar_one()
        under_review_transactions = self.db.execute(
            select(func.count(Transaction.id)).where(Transaction.status == TransactionStatus.UNDER_REVIEW)
        ).scalar_one()
        pending_transactions = self.db.execute(
            select(func.count(Transaction.id)).where(Transaction.status == TransactionStatus.PENDING)
        ).scalar_one()
        failed_transactions = self.db.execute(
            select(func.count(Transaction.id)).where(Transaction.status == TransactionStatus.FAILED)
        ).scalar_one()

        # Volume
        total_volume = self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount_usd), 0))
        ).scalar_one()

        # Risk stats
        avg_risk = self.db.execute(
            select(func.coalesce(func.avg(Transaction.risk_score), 0))
        ).scalar_one()

        # Risk distribution buckets (mutually exclusive, covering 0-100)
        low_risk = self.db.execute(
            select(func.count(Transaction.id)).where(Transaction.risk_score.between(0, 30))
        ).scalar_one()

        medium_risk = self.db.execute(
            select(func.count(Transaction.id)).where(Transaction.risk_score.between(31, 69))
        ).scalar_one()

        high_risk = self.db.execute(
            select(func.count(Transaction.id)).where(Transaction.risk_score.between(70, 89))
        ).scalar_one()

        critical_risk = self.db.execute(
            select(func.count(Transaction.id)).where(Transaction.risk_score.between(90, 100))
        ).scalar_one()

        # Legacy fields for backward compatibility
        # high_risk_transactions (legacy) = high + critical (>=70)
        legacy_high_risk = high_risk + critical_risk
        legacy_critical_risk = critical_risk

        # Security events (last 24 hours)
        since = datetime.utcnow() - timedelta(hours=24)
        recent_events = self.db.execute(
            select(func.count(SecurityEvent.id)).where(SecurityEvent.detected_at >= since)
        ).scalar_one()

        unacknowledged = self.db.execute(
            select(func.count(SecurityEvent.id)).where(SecurityEvent.acknowledged_at.is_(None))
        ).scalar_one()

        return DashboardSummary(
            total_agents=total_agents,
            active_agents=active_agents,
            suspended_agents=suspended_agents,
            pending_review_agents=pending_review_agents,
            total_transactions=total_transactions,
            approved_transactions=approved_transactions,
            blocked_transactions=blocked_transactions,
            under_review_transactions=under_review_transactions,
            pending_transactions=pending_transactions,
            failed_transactions=failed_transactions,
            total_volume_usd=float(total_volume),
            avg_risk_score=float(avg_risk),
            low_risk_transactions=low_risk,
            medium_risk_transactions=medium_risk,
            high_risk_transactions=high_risk,
            critical_risk_transactions=critical_risk,
            recent_security_events=recent_events,
            unacknowledged_events=unacknowledged,
        )


class SecurityEventService:
    """Service for security event operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_security_events(
        self,
        params: PaginationParams,
        agent_id: Optional[int] = None,
        transaction_id: Optional[int] = None,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> PaginatedResponse[SecurityEventResponse]:
        """Get paginated security events with filters."""
        query = select(SecurityEvent)
        count_query = select(func.count(SecurityEvent.id))

        if agent_id:
            query = query.where(SecurityEvent.agent_id == agent_id)
            count_query = count_query.where(SecurityEvent.agent_id == agent_id)

        if transaction_id:
            query = query.where(SecurityEvent.transaction_id == transaction_id)
            count_query = count_query.where(SecurityEvent.transaction_id == transaction_id)

        if event_type:
            query = query.where(SecurityEvent.event_type == event_type)
            count_query = count_query.where(SecurityEvent.event_type == event_type)

        if severity:
            query = query.where(SecurityEvent.severity == severity)
            count_query = count_query.where(SecurityEvent.severity == severity)

        total = self.db.execute(count_query).scalar_one()

        query = query.order_by(SecurityEvent.detected_at.desc())
        query = query.offset((params.page - 1) * params.page_size).limit(params.page_size)

        events = self.db.execute(query).scalars().all()
        items = [SecurityEventResponse.model_validate(event) for event in events]

        return PaginatedResponse.create(items, total, params.page, params.page_size)


# Import case for use in AgentService
from sqlalchemy import case