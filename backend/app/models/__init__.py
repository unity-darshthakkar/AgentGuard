"""SQLAlchemy models for AgentGuard."""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CredentialStatus(str, enum.Enum):
    """Agent credential status."""

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class PolicyStatus(str, enum.Enum):
    """Spending policy status."""

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class AuthorizationDecision(str, enum.Enum):
    """Authorization decision outcome."""

    ALLOW = "allow"
    BLOCK = "block"
    REVIEW = "review"


class AgentStatus(str, enum.Enum):
    """Agent operational status."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING_REVIEW = "pending_review"
    DECOMMISSIONED = "decommissioned"


class TransactionStatus(str, enum.Enum):
    """Payment transaction status."""

    APPROVED = "approved"
    BLOCKED = "blocked"
    UNDER_REVIEW = "under_review"
    PENDING = "pending"
    FAILED = "failed"


class ReservationStatus(str, enum.Enum):
    """Authorization reservation lifecycle status."""

    RESERVED = "reserved"
    CAPTURED = "captured"
    RELEASED = "released"
    EXPIRED = "expired"


class SecurityEventType(str, enum.Enum):
    """Types of security events."""

    VELOCITY_ANOMALY = "velocity_anomaly"
    GEO_ANOMALY = "geo_anomaly"
    AMOUNT_OUTLIER = "amount_outlier"
    NEW_MERCHANT = "new_merchant"
    PERMISSION_VIOLATION = "permission_violation"
    PATTERN_DEVIATION = "pattern_deviation"


class Agent(Base):
    """Autonomous AI agent registered in the system."""

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus, native_enum=False),
        default=AgentStatus.PENDING_REVIEW,
        nullable=False,
        index=True,
    )
    owner_type: Mapped[str] = mapped_column(String(32), nullable=False)  # "human" or "organization"
    owner_name: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_email: Mapped[str] = mapped_column(String(256), nullable=False)
    owner_contact: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # Spending permissions (display only in Phase 1)
    daily_limit_usd: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    monthly_limit_usd: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    allowed_merchant_categories: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    blocked_merchant_categories: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="agent", lazy="dynamic"
    )
    security_events: Mapped[list["SecurityEvent"]] = relationship(
        "SecurityEvent", back_populates="agent", lazy="dynamic"
    )
    credential: Mapped[Optional["AgentCredential"]] = relationship(
        "AgentCredential", back_populates="agent", uselist=False
    )
    spending_policy: Mapped[Optional["SpendingPolicy"]] = relationship(
        "SpendingPolicy", back_populates="agent", uselist=False
    )

    __table_args__ = (
        Index("ix_agents_status_created", "status", "created_at"),
        Index("ix_agents_owner", "owner_type", "owner_email"),
    )

    def __repr__(self) -> str:
        return f"<Agent(id={self.id}, agent_id='{self.agent_id}', name='{self.name}', status='{self.status}')>"


class Transaction(Base):
    """Payment transaction initiated by an agent."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    agent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Transaction details
    amount_usd: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    merchant_name: Mapped[str] = mapped_column(String(128), nullable=False)
    merchant_category: Mapped[str] = mapped_column(String(64), nullable=False)
    merchant_country: Mapped[str] = mapped_column(String(2), nullable=False)  # ISO 3166-1 alpha-2
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Status and risk
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, native_enum=False),
        default=TransactionStatus.PENDING,
        nullable=False,
        index=True,
    )
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0-100
    risk_level: Mapped[str] = mapped_column(String(16), default="low", nullable=False)  # low, medium, high, critical
    decision_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    requested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent", back_populates="transactions")
    security_events: Mapped[list["SecurityEvent"]] = relationship(
        "SecurityEvent", back_populates="transaction", lazy="dynamic"
    )

    __table_args__ = (
        Index("ix_transactions_agent_status", "agent_id", "status"),
        Index("ix_transactions_requested", "requested_at"),
        Index("ix_transactions_risk", "risk_score", "risk_level"),
    )

    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, transaction_id='{self.transaction_id}', amount={self.amount_usd}, status='{self.status}')>"


class SecurityEvent(Base):
    """Security event detected for a transaction or agent."""

    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    agent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transaction_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    event_type: Mapped[SecurityEventType] = mapped_column(
        Enum(SecurityEventType, native_enum=False), nullable=False, index=True
    )
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False)  # info, warning, critical
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON details

    # Metadata
    detected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent", back_populates="security_events")
    transaction: Mapped[Optional["Transaction"]] = relationship("Transaction", back_populates="security_events")

    __table_args__ = (
        Index("ix_security_events_agent_type", "agent_id", "event_type"),
        Index("ix_security_events_detected", "detected_at"),
    )

    def __repr__(self) -> str:
        return f"<SecurityEvent(id={self.id}, event_id='{self.event_id}', type='{self.event_type}', severity='{self.severity}')>"


class AgentCredential(Base):
    """Cryptographic credential for agent identity verification."""

    __tablename__ = "agent_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True, unique=True
    )

    # Key identification
    key_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)  # PEM-encoded Ed25519 public key
    algorithm: Mapped[str] = mapped_column(String(32), default="Ed25519", nullable=False)

    # Status and lifecycle
    status: Mapped[CredentialStatus] = mapped_column(
        Enum(CredentialStatus, native_enum=False),
        default=CredentialStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    revocation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent", back_populates="credential")

    __table_args__ = (
        Index("ix_agent_credentials_status_expires", "status", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<AgentCredential(id={self.id}, agent_id={self.agent_id}, key_id='{self.key_id}', status='{self.status}')>"


class SpendingPolicy(Base):
    """Delegated spending authorization policy for an agent."""

    __tablename__ = "spending_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True, unique=True
    )
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # References owner who created policy

    # Policy limits (stored as integer minor units - cents for USD)
    per_transaction_limit_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    daily_budget_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    allowed_currencies: Mapped[str] = mapped_column(String(128), nullable=False)  # JSON array of ISO 4217 codes
    allowed_merchant_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    blocked_merchant_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array

    # Policy lifecycle
    status: Mapped[PolicyStatus] = mapped_column(
        Enum(PolicyStatus, native_enum=False),
        default=PolicyStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    effective_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent", back_populates="spending_policy")

    __table_args__ = (
        Index("ix_spending_policies_status_expires", "status", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<SpendingPolicy(id={self.id}, agent_id={self.agent_id}, daily_budget={self.daily_budget_cents} cents, status='{self.status}')>"


class AuthorizationDecisionRecord(Base):
    """Audit record of authorization decisions for payment intents."""

    __tablename__ = "authorization_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Request identification
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    # Agent and policy
    agent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    credential_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent_credentials.id", ondelete="SET NULL"), nullable=True
    )
    policy_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("spending_policies.id", ondelete="SET NULL"), nullable=True
    )

    # Payment intent details
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    merchant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    merchant_category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Decision
    decision: Mapped[AuthorizationDecision] = mapped_column(
        Enum(AuthorizationDecision, native_enum=False), nullable=False, index=True
    )
    reasons: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array of reason strings
    policy_violations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array

    # Budget tracking (snapshot at decision time)
    daily_spent_before_cents: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    daily_spent_after_cents: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Anomaly Detection / Risk Scoring (Phase 4)
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0-100
    risk_level: Mapped[str] = mapped_column(String(16), default="minimal", nullable=False)  # minimal, low, medium, high, critical
    anomaly_signals: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of signal objects
    anomaly_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Human-readable explanation
    detection_method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # rule_based, ml_based

    # Metadata
    decided_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False, index=True)

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent")
    credential: Mapped[Optional["AgentCredential"]] = relationship("AgentCredential")
    policy: Mapped[Optional["SpendingPolicy"]] = relationship("SpendingPolicy")
    reservation: Mapped[Optional["AuthorizationReservation"]] = relationship(
        "AuthorizationReservation", back_populates="auth_decision", uselist=False
    )

    __table_args__ = (
        Index("ix_auth_decisions_agent_decided", "agent_id", "decided_at"),
        Index("ix_auth_decisions_idempotency", "idempotency_key", unique=True),
        Index("ix_auth_decisions_risk", "risk_score", "risk_level"),
    )

    def __repr__(self) -> str:
        return f"<AuthorizationDecisionRecord(id={self.id}, request_id='{self.request_id}', decision='{self.decision}', amount={self.amount_cents} cents, risk={self.risk_score})>"


class NonceStore(Base):
    """Single-use nonce store for replay attack prevention."""

    __tablename__ = "nonce_store"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nonce: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    agent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    used_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index("ix_nonce_store_agent_expires", "agent_id", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<NonceStore(nonce='{self.nonce}', agent_id={self.agent_id})>"


class DailyBudgetUsage(Base):
    """
    Tracks daily budget reservations and captured spending for an agent.

    This table enables atomic budget reservations by using a single row per
    (agent_id, UTC date) that tracks:
    - reserved_cents: Amount currently reserved by ALLOW decisions not yet captured
    - captured_cents: Amount actually captured via PayPal (Phase 3+)
    - The sum (reserved_cents + captured_cents) must not exceed the policy's daily_budget_cents

    Budget reservation is performed atomically using an UPDATE with a WHERE clause
    that checks the budget constraint. This is SQLite-compatible and avoids
    race conditions without requiring SELECT FOR UPDATE.
    """

    __tablename__ = "daily_budget_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    usage_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)  # Start of UTC day
    daily_budget_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reserved_cents: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    captured_cents: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_daily_budget_usage_agent_date", "agent_id", "usage_date", unique=True),
    )

    def __repr__(self) -> str:
        return f"<DailyBudgetUsage(agent_id={self.agent_id}, date={self.usage_date}, reserved={self.reserved_cents}, captured={self.captured_cents})>"


class AuthorizationReservation(Base):
    """
    Tracks authorization-specific budget reservations with lifecycle management.

    Each reservation is linked to exactly one AuthorizationDecisionRecord and
    represents a budget hold for a specific payment authorization. The reservation
    lifecycle ensures proper budget accounting from authorization through capture
    or release.

    Lifecycle states:
    - RESERVED: Budget held for an ALLOW authorization, awaiting capture/release
    - CAPTURED: Payment completed, budget moved from reserved to captured
    - RELEASED: Authorization cancelled/expired, budget returned to available
    - EXPIRED: Reservation expired without capture, budget returned to available

    Transitions:
    - RESERVED -> CAPTURED (capture)
    - RESERVED -> RELEASED (release)
    - RESERVED -> EXPIRED (expiration)
    - CAPTURED -> (terminal)
    - RELEASED -> (terminal)
    - EXPIRED -> (terminal)

    All transitions are idempotent and use atomic conditional updates for
    SQLite-compatible concurrency safety.
    """

    __tablename__ = "authorization_reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Link to authorization decision
    auth_decision_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("authorization_decisions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    # Agent and policy snapshot (for audit and budget reconciliation)
    agent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    policy_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("spending_policies.id", ondelete="SET NULL"), nullable=True
    )

    # Reservation details
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    usage_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)  # UTC budget date

    # Lifecycle
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus, native_enum=False),
        default=ReservationStatus.RESERVED,
        nullable=False,
        index=True,
    )

    # Timestamps
    reserved_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    auth_decision: Mapped["AuthorizationDecisionRecord"] = relationship("AuthorizationDecisionRecord")
    agent: Mapped["Agent"] = relationship("Agent")
    policy: Mapped[Optional["SpendingPolicy"]] = relationship("SpendingPolicy")

    __table_args__ = (
        Index("ix_auth_reservations_agent_status", "agent_id", "status"),
        Index("ix_auth_reservations_usage_date", "usage_date"),
    )

    def __repr__(self) -> str:
        return f"<AuthorizationReservation(id={self.id}, auth_decision_id={self.auth_decision_id}, amount={self.amount_cents} cents, status='{self.status}')>"


import enum


class PayPalOrderStatus(str, enum.Enum):
    """PayPal order orchestration lifecycle status."""

    CREATING = "creating"      # Attempt recorded, PayPal call in progress
    CREATED = "created"        # PayPal order confirmed, approval_url available
    UNKNOWN = "unknown"        # PayPal call timed out - result uncertain, needs reconciliation
    FAILED = "failed"          # PayPal call failed definitively (non-timeout error)


class PayPalOrder(Base):
    """
    Persistent binding between an AgentGuard authorization reservation and a PayPal order.

    This table ensures:
    - One PayPal order per authorization decision (unique auth_decision_id)
    - One PayPal order per reservation (unique reservation_id)
    - Request ID uniqueness to prevent reuse across different purchases
    - Immutable binding - amount, currency, and request_id cannot change after creation
    - Lifecycle tracking for safe retries and reconciliation

    The order attempt is recorded with status=CREATING before the PayPal call.
    On success: status=CREATED with paypal_order_id populated.
    On timeout: status=UNCERTAIN (requires manual reconciliation).
    On other failure: status=FAILED.
    """

    __tablename__ = "paypal_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Links to AgentGuard authorization
    # RESTRICT prevents deletion of authorization/reservation if PayPal order exists (audit trail)
    auth_decision_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("authorization_decisions.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True
    )
    reservation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("authorization_reservations.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True
    )

    # PayPal order details
    # paypal_order_id is NULL during CREATING, populated on CREATED
    paypal_order_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True, nullable=True)
    paypal_request_id: Mapped[str] = mapped_column(String(108), unique=True, index=True, nullable=False)

    # Amount and currency (derived from reservation, never from client)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    # PayPal order orchestration status
    # values_callable ensures the enum VALUE (lowercase) is stored, not the NAME (uppercase)
    status: Mapped[PayPalOrderStatus] = mapped_column(
        Enum(PayPalOrderStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=PayPalOrderStatus.CREATING,
        nullable=False,
        index=True,
    )

    # Buyer approval URL (for redirect) - populated on CREATED
    approval_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    auth_decision: Mapped["AuthorizationDecisionRecord"] = relationship("AuthorizationDecisionRecord")
    reservation: Mapped["AuthorizationReservation"] = relationship("AuthorizationReservation")

    __table_args__ = (
        # Prevent reuse of request_id across different purchases
        Index("ix_paypal_orders_request_id", "paypal_request_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<PayPalOrder(id={self.id}, paypal_order_id='{self.paypal_order_id}', auth_decision_id={self.auth_decision_id}, status='{self.status}')>"


class PayPalCaptureStatus(str, enum.Enum):
    """PayPal capture orchestration lifecycle status."""

    CAPTURING = "capturing"    # Attempt recorded, PayPal capture call in progress
    COMPLETED = "completed"    # PayPal capture confirmed, funds captured
    UNKNOWN = "unknown"        # PayPal call timed out - result uncertain, needs reconciliation
    FAILED = "failed"          # PayPal call failed definitively (non-timeout error)


class PayPalCapture(Base):
    """
    Persistent record of a PayPal capture attempt linked to a PayPal order.

    This table ensures:
    - One capture attempt per PayPal order (unique paypal_order_id)
    - Stable capture-specific PayPal-Request-Id for idempotency
    - Capture ID, status, amount, and currency when confirmed
    - Lifecycle tracking for safe retries and reconciliation

    The capture attempt is recorded with status=CAPTURING before the PayPal call.
    On success: status=COMPLETED with paypal_capture_id populated.
    On timeout: status=UNKNOWN (requires manual reconciliation).
    On other failure: status=FAILED.
    """

    __tablename__ = "paypal_captures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Link to PayPal order
    paypal_order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("paypal_orders.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True
    )

    # PayPal capture details
    # paypal_capture_id is NULL during CAPTURING, populated on COMPLETED
    paypal_capture_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True, nullable=True)
    paypal_request_id: Mapped[str] = mapped_column(String(108), unique=True, index=True, nullable=False)

    # Amount and currency (derived from reservation, verified against PayPal response)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    # PayPal capture orchestration status
    status: Mapped[PayPalCaptureStatus] = mapped_column(
        Enum(PayPalCaptureStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=PayPalCaptureStatus.CAPTURING,
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    paypal_order: Mapped["PayPalOrder"] = relationship("PayPalOrder")

    __table_args__ = (
        # Prevent reuse of capture request_id across different purchases
        Index("ix_paypal_captures_request_id", "paypal_request_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<PayPalCapture(id={self.id}, paypal_capture_id='{self.paypal_capture_id}', paypal_order_id={self.paypal_order_id}, status='{self.status}')>"