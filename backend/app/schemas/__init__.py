"""Pydantic schemas for API requests and responses."""

from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Base Schemas
# =============================================================================

class BaseSchema(BaseModel):
    """Base schema with common configuration."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PaginationParams(BaseModel):
    """Pagination query parameters."""
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")


T = TypeVar("T")


class PaginatedResponse(BaseSchema, Generic[T]):
    """Generic paginated response wrapper."""
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(cls, items: List[T], total: int, page: int, page_size: int) -> "PaginatedResponse[T]":
        """Create paginated response from items and pagination info."""
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if page_size > 0 else 0,
        )


# =============================================================================
# Agent Schemas
# =============================================================================

class AgentBase(BaseSchema):
    """Base agent fields."""
    agent_id: str
    name: str
    description: Optional[str] = None
    status: str
    owner_type: str
    owner_name: str
    owner_email: str
    owner_contact: Optional[str] = None
    daily_limit_usd: float
    monthly_limit_usd: float
    allowed_merchant_categories: Optional[str] = None
    blocked_merchant_categories: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_active_at: Optional[datetime] = None


class AgentResponse(AgentBase):
    """Agent response with ID."""
    id: int

    model_config = ConfigDict(from_attributes=True)


class AgentListResponse(PaginatedResponse):
    """Paginated agent list response."""
    items: List[AgentResponse]


class AgentDetailResponse(AgentResponse):
    """Detailed agent response with transaction summary."""
    transaction_count: int = 0
    approved_count: int = 0
    blocked_count: int = 0
    under_review_count: int = 0
    total_volume_usd: float = 0.0
    avg_risk_score: float = 0.0


# =============================================================================
# Transaction Schemas
# =============================================================================

class TransactionBase(BaseSchema):
    """Base transaction fields."""
    transaction_id: str
    agent_id: int
    amount_usd: float
    currency: str
    merchant_name: str
    merchant_category: str
    merchant_country: str
    description: Optional[str] = None
    status: str
    risk_score: int
    risk_level: str
    decision_reason: Optional[str] = None
    requested_at: datetime
    decided_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class TransactionResponse(TransactionBase):
    """Transaction response with ID."""
    id: int

    model_config = ConfigDict(from_attributes=True)


class TransactionListResponse(PaginatedResponse):
    """Paginated transaction list response."""
    items: List[TransactionResponse]


class TransactionDetailResponse(TransactionResponse):
    """Detailed transaction response with agent info and security events."""
    agent: Optional[AgentResponse] = None
    security_events: List["SecurityEventResponse"] = []


# =============================================================================
# Security Event Schemas
# =============================================================================

class SecurityEventBase(BaseSchema):
    """Base security event fields."""
    event_id: str
    agent_id: int
    transaction_id: Optional[int] = None
    event_type: str
    severity: str
    title: str
    description: Optional[str] = None
    details_json: Optional[str] = None
    detected_at: datetime
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None


class SecurityEventResponse(SecurityEventBase):
    """Security event response with ID."""
    id: int

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Dashboard Schemas
# =============================================================================

class DashboardSummary(BaseSchema):
    """Dashboard KPI summary."""
    total_agents: int
    active_agents: int
    suspended_agents: int
    pending_review_agents: int
    total_transactions: int
    approved_transactions: int
    blocked_transactions: int
    under_review_transactions: int
    pending_transactions: int
    failed_transactions: int
    total_volume_usd: float
    avg_risk_score: float
    # Risk distribution buckets (mutually exclusive, covering 0-100)
    low_risk_transactions: int      # 0-30
    medium_risk_transactions: int   # 31-69
    high_risk_transactions: int     # 70-89
    critical_risk_transactions: int # 90-100
    # Legacy fields (deprecated, kept for backward compatibility)
    # high_risk_transactions includes critical (>=70)
    # critical_risk_transactions (>=90)
    recent_security_events: int
    unacknowledged_events: int


class HealthResponse(BaseSchema):
    """Health check response."""
    status: str
    version: str
    database: str
    timestamp: datetime


# =============================================================================
# Authentication & Credential Schemas
# =============================================================================

class AgentRegistrationRequest(BaseSchema):
    """Request to register a new agent with a public key."""
    agent_id: str = Field(..., min_length=1, max_length=64, description="Unique agent identifier")
    name: str = Field(..., min_length=1, max_length=128, description="Agent display name")
    description: Optional[str] = Field(None, max_length=1000)
    owner_type: str = Field(..., pattern="^(human|organization)$")
    owner_name: str = Field(..., min_length=1, max_length=128)
    owner_email: str = Field(..., max_length=256)
    owner_contact: Optional[str] = Field(None, max_length=256)
    public_key_pem: str = Field(..., description="PEM-encoded Ed25519 public key")
    expires_in_days: Optional[int] = Field(None, ge=1, le=3650, description="Credential validity in days")


class AgentRegistrationResponse(BaseSchema):
    """Response after agent registration."""
    agent_id: str
    key_id: str
    credential_id: int
    issued_at: datetime
    expires_at: Optional[datetime] = None
    message: str


class CredentialResponse(BaseSchema):
    """Agent credential response (public key excluded for security)."""
    id: int
    agent_id: int
    key_id: str
    algorithm: str
    status: str
    issued_at: datetime
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[str] = None
    revocation_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CredentialRevokeRequest(BaseSchema):
    """Request to revoke an agent credential."""
    reason: str = Field(..., min_length=1, max_length=500, description="Revocation reason")


class CredentialStatusResponse(BaseSchema):
    """Credential status check response."""
    key_id: str
    status: str
    is_valid: bool
    expires_at: Optional[datetime] = None
    message: str


class NonceResponse(BaseSchema):
    """Nonce challenge response for signing."""
    nonce: str
    expires_at: datetime
    message: str


# =============================================================================
# Spending Policy Schemas
# =============================================================================

class SpendingPolicyCreateRequest(BaseSchema):
    """Request to create a spending policy for an agent.

    owner_id is derived from the agent's registered owner (owner_type:owner_email),
    not provided in the request body. This prevents owner spoofing.
    """
    per_transaction_limit_cents: int = Field(..., ge=1, description="Maximum amount per transaction in minor units (cents)")
    daily_budget_cents: int = Field(..., ge=1, description="Daily spending budget in minor units (cents)")
    allowed_currencies: List[str] = Field(..., min_length=1, description="List of allowed ISO 4217 currency codes")
    allowed_merchant_ids: Optional[List[str]] = Field(None, description="Optional list of allowed merchant identifiers")
    blocked_merchant_ids: Optional[List[str]] = Field(None, description="Optional list of blocked merchant identifiers")
    expires_in_days: Optional[int] = Field(None, ge=1, le=3650, description="Policy validity in days")


class SpendingPolicyUpdateRequest(BaseSchema):
    """Request to update a spending policy (only non-financial fields)."""
    allowed_merchant_ids: Optional[List[str]] = None
    blocked_merchant_ids: Optional[List[str]] = None
    expires_in_days: Optional[int] = Field(None, ge=1, le=3650)


class SpendingPolicyRevokeRequest(BaseSchema):
    """Request to revoke a spending policy."""
    reason: str = Field(..., min_length=1, max_length=500)


class SpendingPolicyResponse(BaseSchema):
    """Spending policy response."""
    id: int
    agent_id: int
    owner_id: str
    per_transaction_limit_cents: int
    daily_budget_cents: int
    allowed_currencies: List[str]
    allowed_merchant_ids: Optional[List[str]] = None
    blocked_merchant_ids: Optional[List[str]] = None
    status: str
    effective_at: datetime
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Authorization Schemas
# =============================================================================

class AuthorizationRequest(BaseSchema):
    """Payment authorization request from an agent."""
    request_id: str = Field(..., min_length=1, max_length=64, description="Unique request identifier")
    idempotency_key: Optional[str] = Field(None, max_length=128, description="Idempotency key for duplicate prevention")
    agent_id: str = Field(..., min_length=1, max_length=64, description="Agent identifier")
    key_id: str = Field(..., min_length=1, max_length=64, description="Credential key identifier")
    nonce: str = Field(..., min_length=1, max_length=64, description="Single-use nonce from challenge endpoint")
    timestamp: datetime = Field(..., description="Request timestamp (ISO 8601)")
    signature: str = Field(..., min_length=1, description="Ed25519 signature of canonical request")

    # Payment intent
    amount_cents: int = Field(..., ge=1, description="Transaction amount in minor units (cents)")
    currency: str = Field(..., min_length=3, max_length=3, pattern="^[A-Z]{3}$", description="ISO 4217 currency code")
    merchant_id: str = Field(..., min_length=1, max_length=128, description="Merchant identifier")
    merchant_category: str = Field(..., min_length=1, max_length=64, description="Merchant category")
    description: Optional[str] = Field(None, max_length=1000, description="Transaction description")


class AuthorizationResponse(BaseSchema):
    """Authorization decision response."""
    request_id: str
    decision: str  # allow, block, review
    reasons: List[str]
    policy_violations: Optional[List[str]] = None
    daily_spent_before_cents: int
    daily_spent_after_cents: int
    daily_budget_remaining_cents: int
    decided_at: datetime

    # Risk Scoring (Phase 4)
    risk_score: int = 0  # 0-100
    risk_level: str = "minimal"  # minimal, low, medium, high, critical
    anomaly_signals: List[dict] = []  # List of anomaly signal objects
    anomaly_explanation: Optional[str] = None  # Human-readable explanation
    detection_method: Optional[str] = None  # rule_based, ml_based


class AuthorizationDecisionResponse(BaseSchema):
    """Authorization decision audit record response."""
    id: int
    request_id: str
    idempotency_key: Optional[str] = None
    agent_id: int
    credential_id: Optional[int] = None
    policy_id: Optional[int] = None
    amount_cents: int
    currency: str
    merchant_id: str
    merchant_category: str
    description: Optional[str] = None
    decision: str
    reasons: List[str]
    policy_violations: Optional[List[str]] = None
    daily_spent_before_cents: int
    daily_spent_after_cents: int
    decided_at: datetime

    # Risk Scoring (Phase 4)
    risk_score: int = 0
    risk_level: str = "minimal"
    anomaly_signals: Optional[str] = None  # JSON string
    anomaly_explanation: Optional[str] = None
    detection_method: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AuthorizationDecisionListResponse(PaginatedResponse):
    """Paginated authorization decision list response."""
    items: List[AuthorizationDecisionResponse]


# =============================================================================
# Authorization Reservation Schemas
# =============================================================================

class AuthorizationReservationResponse(BaseSchema):
    """Authorization reservation response."""
    id: int
    auth_decision_id: int
    agent_id: int
    policy_id: Optional[int] = None
    amount_cents: int
    currency: str
    usage_date: datetime
    status: str  # reserved, captured, released, expired
    reserved_at: datetime
    captured_at: Optional[datetime] = None
    released_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuthorizationReservationListResponse(PaginatedResponse):
    """Paginated authorization reservation list response."""
    items: List[AuthorizationReservationResponse]


class ReservationCaptureRequest(BaseSchema):
    """Request to capture a reservation (admin only)."""
    auth_decision_id: int = Field(..., description="Authorization decision ID")
    agent_id: int = Field(..., description="Agent ID for verification")
    amount_cents: int = Field(..., ge=1, description="Amount to capture in minor units (cents)")
    usage_date: Optional[datetime] = Field(None, description="UTC budget date (defaults to today)")


class ReservationReleaseRequest(BaseSchema):
    """Request to release a reservation (admin only)."""
    auth_decision_id: int = Field(..., description="Authorization decision ID")
    agent_id: int = Field(..., description="Agent ID for verification")
    amount_cents: int = Field(..., ge=1, description="Amount to release in minor units (cents)")
    usage_date: Optional[datetime] = Field(None, description="UTC budget date (defaults to today)")


class ReservationExpireRequest(BaseSchema):
    """Request to expire old reservations (admin only)."""
    max_age_hours: int = Field(default=24, ge=1, le=168, description="Maximum age in hours for RESERVED reservations")


class ReservationLifecycleResponse(BaseSchema):
    """Response for reservation lifecycle operations."""
    success: bool
    message: str
    reservation: Optional[AuthorizationReservationResponse] = None


# =============================================================================
# Checkout Schemas
# =============================================================================


class CheckoutStartRequest(BaseSchema):
    """Request to start a PayPal sandbox checkout for an authorized decision."""
    authorization_decision_id: int = Field(..., description="The authorization decision ID")


class CheckoutStartResponse(BaseSchema):
    """Response after starting checkout."""
    authorization_decision_id: int
    reservation_id: int
    paypal_order_id: str
    approval_url: str
    checkout_status: str  # created, pending_approval, completed, timeout, failed
    reservation_status: str  # reserved, captured, released, expired
    message: str


class CheckoutStatusResponse(BaseSchema):
    """Checkout status response."""
    authorization_decision_id: int
    request_id: str
    agent_id: int
    amount_cents: int
    currency: str
    merchant_id: str
    merchant_category: str
    description: Optional[str] = None
    decision: str  # allow, block, review
    reservation_status: str  # reserved, captured, released, expired
    paypal_order_status: Optional[str] = None  # creating, created, unknown, failed
    paypal_order_id: Optional[str] = None
    approval_url: Optional[str] = None
    paypal_capture_status: Optional[str] = None  # capturing, completed, unknown, failed
    paypal_capture_id: Optional[str] = None
    reconciliation_required: bool = False
    reconciliation_reason: Optional[str] = None
    decided_at: datetime
    reserved_at: Optional[datetime] = None
    captured_at: Optional[datetime] = None


class CheckoutCaptureResponse(BaseSchema):
    """Response after capturing a PayPal order."""
    authorization_decision_id: int
    reservation_id: int
    paypal_order_id: str
    paypal_capture_id: Optional[str] = None
    capture_status: str  # completed, unknown, failed
    reservation_status: str  # captured
    reconciliation_required: bool = False
    reconciliation_reason: Optional[str] = None
    message: str


# =============================================================================
# Forward references
# =============================================================================
TransactionDetailResponse.model_rebuild()