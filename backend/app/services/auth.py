"""Authentication service for cryptographic agent identity verification."""

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy import delete, select, func, update
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    AgentCredential,
    AuthorizationDecision,
    AuthorizationDecisionRecord,
    AuthorizationReservation,
    CredentialStatus,
    DailyBudgetUsage,
    NonceStore,
    PolicyStatus,
    ReservationStatus,
    SpendingPolicy,
)


# =============================================================================
# Constants
# =============================================================================

# Nonce expiration window (5 minutes)
NONCE_TTL_SECONDS = 300

# Request timestamp tolerance (2 minutes)
TIMESTAMP_TOLERANCE_SECONDS = 120

# Canonical request fields for signing (in order)
SIGNATURE_FIELDS = [
    "method",
    "path",
    "timestamp",
    "nonce",
    "body_hash",
]


# =============================================================================
# Cryptographic Utilities
# =============================================================================


def load_public_key(pem: str) -> ed25519.Ed25519PublicKey:
    """Load Ed25519 public key from PEM string."""
    return serialization.load_pem_public_key(pem.encode())


def verify_signature(
    public_key: ed25519.Ed25519PublicKey,
    message: bytes,
    signature_b64: str,
) -> bool:
    """Verify Ed25519 signature (base64 encoded only)."""
    try:
        signature = __import__("base64").b64decode(signature_b64)
        public_key.verify(signature, message)
        return True
    except (InvalidSignature, ValueError, Exception):
        return False


def canonical_request_string(
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    body_hash: str,
) -> str:
    """Create canonical request string for signing."""
    return "\n".join([method.upper(), path, timestamp, nonce, body_hash])


def compute_body_hash(body: dict) -> str:
    """Compute SHA-256 hash of canonical JSON body."""
    # Sort keys for deterministic hashing
    canonical_json = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode()).hexdigest()


def generate_nonce() -> str:
    """Generate a cryptographically secure random nonce."""
    return secrets.token_urlsafe(32)


def generate_key_id() -> str:
    """Generate a unique key identifier."""
    return f"key-{secrets.token_urlsafe(16)}"


def generate_request_id() -> str:
    """Generate a unique request identifier."""
    return f"req-{int(time.time() * 1000)}-{secrets.token_urlsafe(8)}"


# =============================================================================
# Nonce Management
# =============================================================================


def _now_utc_naive() -> datetime:
    """Return current UTC time as naive datetime (for DB compatibility)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_nonce(db: Session, agent_id: int) -> Tuple[str, datetime]:
    """Create and store a new nonce for an agent."""
    nonce = generate_nonce()
    expires_at = _now_utc_naive() + timedelta(seconds=NONCE_TTL_SECONDS)

    nonce_record = NonceStore(
        nonce=nonce,
        agent_id=agent_id,
        expires_at=expires_at,
    )
    db.add(nonce_record)
    db.commit()

    return nonce, expires_at


def consume_nonce(db: Session, agent_id: int, nonce: str) -> bool:
    """Atomically consume a nonce (prevent replay). Returns True if valid and consumed.

    Does NOT commit - caller must commit the transaction.
    """
    # Delete the nonce if it exists and hasn't expired
    now = _now_utc_naive()
    result = db.execute(
        delete(NonceStore).where(
            NonceStore.nonce == nonce,
            NonceStore.agent_id == agent_id,
            NonceStore.expires_at > now,
        )
    )
    # No commit - let caller handle transaction
    return result.rowcount > 0


def cleanup_expired_nonces(db: Session) -> int:
    """Clean up expired nonces. Returns count of deleted records."""
    now = _now_utc_naive()
    result = db.execute(
        delete(NonceStore).where(NonceStore.expires_at <= now)
    )
    db.commit()
    return result.rowcount


# =============================================================================
# Credential Management
# =============================================================================


def register_agent_credential(
    db: Session,
    agent: Agent,
    public_key_pem: str,
    expires_in_days: Optional[int] = None,
) -> AgentCredential:
    """Register a new credential for an agent."""
    # Load and validate the public key
    public_key = load_public_key(public_key_pem)
    if not isinstance(public_key, ed25519.Ed25519PublicKey):
        raise ValueError("Only Ed25519 keys are supported")

    # Generate key ID
    key_id = generate_key_id()

    # Calculate expiration
    issued_at = _now_utc_naive()
    expires_at = issued_at + timedelta(days=expires_in_days) if expires_in_days else None

    credential = AgentCredential(
        agent_id=agent.id,
        key_id=key_id,
        public_key=public_key_pem,
        algorithm="Ed25519",
        status=CredentialStatus.ACTIVE,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    db.add(credential)
    db.commit()
    db.refresh(credential)

    return credential


def get_active_credential(db: Session, agent_id: int, key_id: str) -> Optional[AgentCredential]:
    """Get active credential for agent and key_id."""
    return db.execute(
        select(AgentCredential).where(
            AgentCredential.agent_id == agent_id,
            AgentCredential.key_id == key_id,
            AgentCredential.status == CredentialStatus.ACTIVE,
        )
    ).scalar_one_or_none()


def revoke_credential(
    db: Session,
    credential: AgentCredential,
    revoked_by: str,
    reason: str,
) -> AgentCredential:
    """Revoke an agent credential."""
    credential.status = CredentialStatus.REVOKED
    credential.revoked_at = _now_utc_naive()
    credential.revoked_by = revoked_by
    credential.revocation_reason = reason
    db.commit()
    db.refresh(credential)
    return credential


def check_credential_valid(credential: AgentCredential) -> Tuple[bool, str]:
    """Check if credential is valid (active, not expired, not revoked)."""
    if credential.status != CredentialStatus.ACTIVE:
        return False, f"Credential is {credential.status.value}"

    if credential.expires_at and credential.expires_at < _now_utc_naive():
        return False, "Credential has expired"

    return True, "Credential is valid"


# =============================================================================
# Spending Policy Management
# =============================================================================


def create_spending_policy(
    db: Session,
    agent: Agent,
    owner_id: str,
    per_transaction_limit_cents: int,
    daily_budget_cents: int,
    allowed_currencies: list[str],
    allowed_merchant_ids: Optional[list[str]] = None,
    blocked_merchant_ids: Optional[list[str]] = None,
    expires_in_days: Optional[int] = None,
) -> SpendingPolicy:
    """Create a spending policy for an agent."""
    effective_at = _now_utc_naive()
    expires_at = effective_at + timedelta(days=expires_in_days) if expires_in_days else None

    policy = SpendingPolicy(
        agent_id=agent.id,
        owner_id=owner_id,
        per_transaction_limit_cents=per_transaction_limit_cents,
        daily_budget_cents=daily_budget_cents,
        allowed_currencies=json.dumps(allowed_currencies),
        allowed_merchant_ids=json.dumps(allowed_merchant_ids) if allowed_merchant_ids else None,
        blocked_merchant_ids=json.dumps(blocked_merchant_ids) if blocked_merchant_ids else None,
        status=PolicyStatus.ACTIVE,
        effective_at=effective_at,
        expires_at=expires_at,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


def get_active_policy(db: Session, agent_id: int) -> Optional[SpendingPolicy]:
    """Get active spending policy for an agent."""
    now = _now_utc_naive()
    return db.execute(
        select(SpendingPolicy).where(
            SpendingPolicy.agent_id == agent_id,
            SpendingPolicy.status == PolicyStatus.ACTIVE,
            SpendingPolicy.effective_at <= now,
        )
    ).scalar_one_or_none()


def revoke_policy(
    db: Session,
    policy: SpendingPolicy,
    revoked_by: str,
) -> SpendingPolicy:
    """Revoke a spending policy."""
    policy.status = PolicyStatus.REVOKED
    policy.revoked_at = _now_utc_naive()
    policy.revoked_by = revoked_by
    db.commit()
    db.refresh(policy)
    return policy


def parse_policy_currencies(policy: SpendingPolicy) -> list[str]:
    """Parse allowed currencies from policy."""
    return json.loads(policy.allowed_currencies)


def parse_policy_allowed_merchants(policy: SpendingPolicy) -> Optional[list[str]]:
    """Parse allowed merchant IDs from policy."""
    if policy.allowed_merchant_ids:
        return json.loads(policy.allowed_merchant_ids)
    return None


def parse_policy_blocked_merchants(policy: SpendingPolicy) -> Optional[list[str]]:
    """Parse blocked merchant IDs from policy."""
    if policy.blocked_merchant_ids:
        return json.loads(policy.blocked_merchant_ids)
    return None


# =============================================================================
# Budget Tracking (Atomic Reservations)
# =============================================================================


def get_daily_spent_cents(db: Session, agent_id: int, date: Optional[datetime] = None) -> int:
    """Get total captured spending in cents for an agent on a given date (UTC day).

    This reads from AuthorizationDecisionRecord for backward compatibility.
    For budget enforcement, use reserve_budget() which uses DailyBudgetUsage.
    """
    if date is None:
        date = _now_utc_naive()

    # Start of day UTC
    start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    result = db.execute(
        select(func.coalesce(func.sum(AuthorizationDecisionRecord.amount_cents), 0))
        .where(
            AuthorizationDecisionRecord.agent_id == agent_id,
            AuthorizationDecisionRecord.decision == AuthorizationDecision.ALLOW,
            AuthorizationDecisionRecord.decided_at >= start_of_day,
            AuthorizationDecisionRecord.decided_at < end_of_day,
        )
    ).scalar_one()

    return int(result)


def _get_usage_date(date: Optional[datetime] = None) -> datetime:
    """Get the start of UTC day for a given date."""
    if date is None:
        date = _now_utc_naive()
    return date.replace(hour=0, minute=0, second=0, microsecond=0)


def reserve_budget(
    db: Session, agent_id: int, amount_cents: int, daily_budget_cents: int, date: Optional[datetime] = None
) -> Tuple[int, int]:
    """
    Atomically reserve budget for an agent's daily spending limit.

    Uses a single atomic UPDATE with a WHERE clause to ensure the reservation
    only succeeds if the budget is not exceeded. This is SQLite-compatible
    and avoids race conditions without requiring SELECT FOR UPDATE.

    The reservation is tracked in DailyBudgetUsage.reserved_cents.
    This is separate from captured spending (DailyBudgetUsage.captured_cents)
    which will be used when PayPal integration is implemented.

    Returns: (daily_reserved_before, daily_reserved_after)

    Raises: ValueError if budget would be exceeded
    """
    usage_date = _get_usage_date(date)

    # Use a single atomic UPDATE with WHERE clause to reserve budget
    # This works in SQLite because the WHERE clause is evaluated atomically
    result = db.execute(
        update(DailyBudgetUsage)
        .where(
            DailyBudgetUsage.agent_id == agent_id,
            DailyBudgetUsage.usage_date == usage_date,
            (DailyBudgetUsage.reserved_cents + DailyBudgetUsage.captured_cents + amount_cents)
            <= DailyBudgetUsage.daily_budget_cents,
        )
        .values(
            reserved_cents=DailyBudgetUsage.reserved_cents + amount_cents,
            updated_at=_now_utc_naive(),
        )
    )

    if result.rowcount > 0:
        # Reservation succeeded, get the new values
        usage = db.execute(
            select(DailyBudgetUsage).where(
                DailyBudgetUsage.agent_id == agent_id,
                DailyBudgetUsage.usage_date == usage_date,
            )
        ).scalar_one()
        reserved_before = usage.reserved_cents - amount_cents
        reserved_after = usage.reserved_cents
        return reserved_before, reserved_after

    # Reservation failed - check if row exists to provide better error message
    existing = db.execute(
        select(DailyBudgetUsage).where(
            DailyBudgetUsage.agent_id == agent_id,
            DailyBudgetUsage.usage_date == usage_date,
        )
    ).scalar_one_or_none()

    if existing:
        current_total = existing.reserved_cents + existing.captured_cents
        raise ValueError(
            f"Daily budget exceeded: would reserve {current_total + amount_cents} cents, "
            f"limit is {existing.daily_budget_cents} cents "
            f"(reserved: {existing.reserved_cents}, captured: {existing.captured_cents})"
        )
    else:
        raise ValueError(
            f"Daily budget exceeded: would reserve {amount_cents} cents, "
            f"limit is {daily_budget_cents} cents (no existing budget row)"
        )


def release_budget(db: Session, agent_id: int, amount_cents: int) -> bool:
    """Release a provisional budget hold before an authorization is recorded."""
    result = db.execute(
        update(DailyBudgetUsage)
        .where(
            DailyBudgetUsage.agent_id == agent_id,
            DailyBudgetUsage.usage_date == _get_usage_date(),
            DailyBudgetUsage.reserved_cents >= amount_cents,
        )
        .values(
            reserved_cents=DailyBudgetUsage.reserved_cents - amount_cents,
            updated_at=_now_utc_naive(),
        )
    )
    return result.rowcount > 0


def ensure_budget_row(
    db: Session, agent_id: int, daily_budget_cents: int, date: Optional[datetime] = None
) -> DailyBudgetUsage:
    """
    Ensure a DailyBudgetUsage row exists for the given agent and date.

    Uses INSERT OR IGNORE (SQLite) / ON CONFLICT DO NOTHING (PostgreSQL)
    to safely handle concurrent first-time initialization.

    Returns the existing or newly created row.
    """
    usage_date = _get_usage_date(date)

    # Try to get existing row first
    existing = db.execute(
        select(DailyBudgetUsage).where(
            DailyBudgetUsage.agent_id == agent_id,
            DailyBudgetUsage.usage_date == usage_date,
        )
    ).scalar_one_or_none()

    if existing:
        return existing

    # Insert new row - use INSERT with ON CONFLICT for atomicity
    # For SQLite, we use INSERT OR IGNORE and then SELECT
    # For PostgreSQL, ON CONFLICT DO NOTHING
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    stmt = sqlite_insert(DailyBudgetUsage).values(
        agent_id=agent_id,
        usage_date=usage_date,
        daily_budget_cents=daily_budget_cents,
        reserved_cents=0,
        captured_cents=0,
    ).on_conflict_do_nothing(index_elements=["agent_id", "usage_date"])

    db.execute(stmt)

    # Fetch the row (either existing or newly inserted)
    return db.execute(
        select(DailyBudgetUsage).where(
            DailyBudgetUsage.agent_id == agent_id,
            DailyBudgetUsage.usage_date == usage_date,
        )
    ).scalar_one()


def release_reservation(
    db: Session, agent_id: int, amount_cents: int, date: Optional[datetime] = None
) -> bool:
    """
    Release a previously reserved budget amount.

    Called when an authorization is cancelled or expires.
    Decrements reserved_cents atomically.

    Returns True if release was successful, False if no matching reservation found.
    """
    usage_date = _get_usage_date(date)

    result = db.execute(
        update(DailyBudgetUsage)
        .where(
            DailyBudgetUsage.agent_id == agent_id,
            DailyBudgetUsage.usage_date == usage_date,
            DailyBudgetUsage.reserved_cents >= amount_cents,
        )
        .values(
            reserved_cents=DailyBudgetUsage.reserved_cents - amount_cents,
            updated_at=_now_utc_naive(),
        )
    )

    return result.rowcount > 0


def capture_spending(
    db: Session, agent_id: int, amount_cents: int, date: Optional[datetime] = None
) -> bool:
    """
    Move reserved amount to captured (for PayPal payment completion).

    Atomically transfers amount from reserved_cents to captured_cents.
    This will be used in Phase 3 when PayPal integration is added.

    Returns True if capture was successful, False if insufficient reservation.
    """
    usage_date = _get_usage_date(date)

    result = db.execute(
        update(DailyBudgetUsage)
        .where(
            DailyBudgetUsage.agent_id == agent_id,
            DailyBudgetUsage.usage_date == usage_date,
            DailyBudgetUsage.reserved_cents >= amount_cents,
        )
        .values(
            reserved_cents=DailyBudgetUsage.reserved_cents - amount_cents,
            captured_cents=DailyBudgetUsage.captured_cents + amount_cents,
            updated_at=_now_utc_naive(),
        )
    )

    return result.rowcount > 0


# =============================================================================
# Authorization Reservation Lifecycle
# =============================================================================


def create_reservation(
    db: Session,
    auth_decision: AuthorizationDecisionRecord,
    agent_id: int,
    policy_id: int,
    amount_cents: int,
    currency: str,
    usage_date: datetime,
) -> AuthorizationReservation:
    """
    Create a new authorization reservation linked to an ALLOW decision.

    This should be called after an authorization is recorded with ALLOW decision.
    The reservation tracks the budget hold for potential capture.

    Returns the created AuthorizationReservation.
    """
    from app.models import AuthorizationReservation, ReservationStatus

    reservation = AuthorizationReservation(
        auth_decision_id=auth_decision.id,
        agent_id=agent_id,
        policy_id=policy_id,
        amount_cents=amount_cents,
        currency=currency.upper(),
        usage_date=usage_date,
        status=ReservationStatus.RESERVED,
    )
    db.add(reservation)
    db.flush()
    return reservation


def capture_reservation(
    db: Session,
    auth_decision_id: int,
    agent_id: int,
    amount_cents: int,
) -> bool:
    """
    Capture a reservation (move from RESERVED to CAPTURED).

    Atomically:
    1. Updates reservation status from RESERVED to CAPTURED
    2. Updates DailyBudgetUsage: reserved_cents -= amount, captured_cents += amount

    This is an idempotent operation - calling it on an already CAPTURED reservation
    returns False (no state change).

    Uses the reservation's stored usage_date for all operations.

    Returns True if capture was successful, False otherwise.
    """
    from app.models import AuthorizationReservation, ReservationStatus, DailyBudgetUsage

    now = _now_utc_naive()

    # First, get the reservation to use its stored usage_date
    reservation = db.execute(
        select(AuthorizationReservation).where(
            AuthorizationReservation.auth_decision_id == auth_decision_id,
            AuthorizationReservation.agent_id == agent_id,
            AuthorizationReservation.amount_cents == amount_cents,
            AuthorizationReservation.status == ReservationStatus.RESERVED,
        )
    ).scalar_one_or_none()

    if reservation is None:
        return False

    usage_date = reservation.usage_date

    # Try to update reservation from RESERVED to CAPTURED
    result = db.execute(
        update(AuthorizationReservation)
        .where(
            AuthorizationReservation.id == reservation.id,
            AuthorizationReservation.status == ReservationStatus.RESERVED,
        )
        .values(
            status=ReservationStatus.CAPTURED,
            captured_at=now,
            updated_at=now,
        )
    )

    if result.rowcount == 0:
        return False

    # Also update DailyBudgetUsage atomically - verify exactly one row affected
    budget_result = db.execute(
        update(DailyBudgetUsage)
        .where(
            DailyBudgetUsage.agent_id == agent_id,
            DailyBudgetUsage.usage_date == usage_date,
            DailyBudgetUsage.reserved_cents >= amount_cents,
        )
        .values(
            reserved_cents=DailyBudgetUsage.reserved_cents - amount_cents,
            captured_cents=DailyBudgetUsage.captured_cents + amount_cents,
            updated_at=now,
        )
    )

    if budget_result.rowcount != 1:
        # Rollback: reservation status change will be rolled back by caller
        raise ValueError(f"Budget update affected {budget_result.rowcount} rows, expected 1")

    return True


def release_reservation(
    db: Session,
    auth_decision_id: int,
    agent_id: int,
    amount_cents: int,
) -> bool:
    """
    Release a reservation (move from RESERVED to RELEASED).

    Atomically:
    1. Updates reservation status from RESERVED to RELEASED
    2. Updates DailyBudgetUsage: reserved_cents -= amount

    This is an idempotent operation - calling it on an already RELEASED reservation
    returns False (no state change).

    Uses the reservation's stored usage_date for all operations.

    Returns True if release was successful, False otherwise.
    """
    from app.models import AuthorizationReservation, ReservationStatus, DailyBudgetUsage

    now = _now_utc_naive()

    # First, get the reservation to use its stored usage_date
    reservation = db.execute(
        select(AuthorizationReservation).where(
            AuthorizationReservation.auth_decision_id == auth_decision_id,
            AuthorizationReservation.agent_id == agent_id,
            AuthorizationReservation.amount_cents == amount_cents,
            AuthorizationReservation.status == ReservationStatus.RESERVED,
        )
    ).scalar_one_or_none()

    if reservation is None:
        return False

    usage_date = reservation.usage_date

    # Try to update reservation from RESERVED to RELEASED
    result = db.execute(
        update(AuthorizationReservation)
        .where(
            AuthorizationReservation.id == reservation.id,
            AuthorizationReservation.status == ReservationStatus.RESERVED,
        )
        .values(
            status=ReservationStatus.RELEASED,
            released_at=now,
            updated_at=now,
        )
    )

    if result.rowcount == 0:
        return False

    # Also update DailyBudgetUsage atomically - verify exactly one row affected
    budget_result = db.execute(
        update(DailyBudgetUsage)
        .where(
            DailyBudgetUsage.agent_id == agent_id,
            DailyBudgetUsage.usage_date == usage_date,
            DailyBudgetUsage.reserved_cents >= amount_cents,
        )
        .values(
            reserved_cents=DailyBudgetUsage.reserved_cents - amount_cents,
            updated_at=now,
        )
    )

    if budget_result.rowcount != 1:
        raise ValueError(f"Budget update affected {budget_result.rowcount} rows, expected 1")

    return True


def expire_reservation(
    db: Session,
    auth_decision_id: int,
    agent_id: int,
    amount_cents: int,
) -> bool:
    """
    Expire a reservation (move from RESERVED to EXPIRED).

    Atomically:
    1. Updates reservation status from RESERVED to EXPIRED
    2. Updates DailyBudgetUsage: reserved_cents -= amount

    This is an idempotent operation - calling it on an already EXPIRED reservation
    returns False (no state change).

    Uses the reservation's stored usage_date for all operations.

    Returns True if expiration was successful, False otherwise.
    """
    from app.models import AuthorizationReservation, ReservationStatus, DailyBudgetUsage

    now = _now_utc_naive()

    # First, get the reservation to use its stored usage_date
    reservation = db.execute(
        select(AuthorizationReservation).where(
            AuthorizationReservation.auth_decision_id == auth_decision_id,
            AuthorizationReservation.agent_id == agent_id,
            AuthorizationReservation.amount_cents == amount_cents,
            AuthorizationReservation.status == ReservationStatus.RESERVED,
        )
    ).scalar_one_or_none()

    if reservation is None:
        return False

    usage_date = reservation.usage_date

    # Try to update reservation from RESERVED to EXPIRED
    result = db.execute(
        update(AuthorizationReservation)
        .where(
            AuthorizationReservation.id == reservation.id,
            AuthorizationReservation.status == ReservationStatus.RESERVED,
        )
        .values(
            status=ReservationStatus.EXPIRED,
            expired_at=now,
            updated_at=now,
        )
    )

    if result.rowcount == 0:
        return False

    # Also update DailyBudgetUsage atomically - verify exactly one row affected
    budget_result = db.execute(
        update(DailyBudgetUsage)
        .where(
            DailyBudgetUsage.agent_id == agent_id,
            DailyBudgetUsage.usage_date == usage_date,
            DailyBudgetUsage.reserved_cents >= amount_cents,
        )
        .values(
            reserved_cents=DailyBudgetUsage.reserved_cents - amount_cents,
            updated_at=now,
        )
    )

    if budget_result.rowcount != 1:
        raise ValueError(f"Budget update affected {budget_result.rowcount} rows, expected 1")

    return True


def get_reservation_by_auth_decision(
    db: Session, auth_decision_id: int
) -> Optional["AuthorizationReservation"]:
    """Get reservation by authorization decision ID."""
    from app.models import AuthorizationReservation

    return db.execute(
        select(AuthorizationReservation).where(
            AuthorizationReservation.auth_decision_id == auth_decision_id
        )
    ).scalar_one_or_none()


def expire_old_reservations(db: Session, max_age_hours: int = 24) -> int:
    """
    Expire reservations older than max_age_hours that are still in RESERVED state.

    This can be run as a periodic cleanup job.

    Returns count of expired reservations.

    Only processes reservations transitioned during this invocation to avoid
    double-releasing budget on repeated calls.
    """
    from app.models import AuthorizationReservation, ReservationStatus, DailyBudgetUsage

    now = _now_utc_naive()
    cutoff = now - timedelta(hours=max_age_hours)

    # FIRST: Select reservations to expire (before updating status)
    # This ensures repeated calls don't double-process the same reservations
    reservations_to_expire = db.execute(
        select(AuthorizationReservation).where(
            AuthorizationReservation.status == ReservationStatus.RESERVED,
            AuthorizationReservation.reserved_at < cutoff,
        )
    ).scalars().all()

    if not reservations_to_expire:
        return 0

    expired_count = 0

    for reservation in reservations_to_expire:
        # Try to update reservation from RESERVED to EXPIRED
        # Use id-based WHERE to ensure we only affect this specific reservation
        result = db.execute(
            update(AuthorizationReservation)
            .where(
                AuthorizationReservation.id == reservation.id,
                AuthorizationReservation.status == ReservationStatus.RESERVED,
            )
            .values(
                status=ReservationStatus.EXPIRED,
                expired_at=now,
                updated_at=now,
            )
        )

        if result.rowcount == 0:
            # Another process already transitioned this reservation
            continue

        # Update DailyBudgetUsage for this specific reservation
        budget_result = db.execute(
            update(DailyBudgetUsage)
            .where(
                DailyBudgetUsage.agent_id == reservation.agent_id,
                DailyBudgetUsage.usage_date == reservation.usage_date,
                DailyBudgetUsage.reserved_cents >= reservation.amount_cents,
            )
            .values(
                reserved_cents=DailyBudgetUsage.reserved_cents - reservation.amount_cents,
                updated_at=now,
            )
        )

        if budget_result.rowcount != 1:
            raise ValueError(
                f"Budget update for reservation {reservation.id} affected "
                f"{budget_result.rowcount} rows, expected 1"
            )

        expired_count += 1

    return expired_count


# =============================================================================
# Authorization Service
# =============================================================================


class AuthorizationService:
    """Service for evaluating payment authorization requests."""

    def __init__(self, db: Session):
        self.db = db

    def evaluate(
        self,
        agent: Agent,
        credential: AgentCredential,
        policy: SpendingPolicy,
        amount_cents: int,
        currency: str,
        merchant_id: str,
        merchant_category: str,
        description: Optional[str],
        idempotency_key: Optional[str],
    ) -> Tuple[AuthorizationDecision, list[str], list[str], int, int]:
        """
        Evaluate a payment authorization request.

        Budget reservation is performed atomically using DailyBudgetUsage table.
        Uses atomic UPDATE with WHERE clause to prevent race conditions.
        This is SQLite-compatible and works in PostgreSQL as well.

        Returns: (decision, reasons, policy_violations, daily_reserved_before, daily_reserved_after)
        """
        reasons = []
        violations = []

        # Check policy status
        if policy.status != PolicyStatus.ACTIVE:
            violations.append(f"Policy is {policy.status.value}")

        # Check policy expiration
        if policy.expires_at and policy.expires_at < _now_utc_naive():
            violations.append("Policy has expired")

        # Check currency
        allowed_currencies = parse_policy_currencies(policy)
        if currency.upper() not in [c.upper() for c in allowed_currencies]:
            violations.append(f"Currency {currency} not in allowed currencies: {allowed_currencies}")

        # Check per-transaction limit
        if amount_cents > policy.per_transaction_limit_cents:
            violations.append(
                f"Amount {amount_cents} cents exceeds per-transaction limit "
                f"{policy.per_transaction_limit_cents} cents"
            )

        # Check merchant allowlist
        allowed_merchants = parse_policy_allowed_merchants(policy)
        if allowed_merchants is not None and merchant_id not in allowed_merchants:
            violations.append(f"Merchant {merchant_id} not in allowed merchant list")

        # Check merchant blocklist
        blocked_merchants = parse_policy_blocked_merchants(policy)
        if blocked_merchants is not None and merchant_id in blocked_merchants:
            violations.append(f"Merchant {merchant_id} is blocked")

        # Check daily budget atomically using reserve_budget
        # Only attempt budget reservation if no other violations so far
        # This ensures budget is not reserved for requests that fail other policy checks
        daily_reserved_before = 0
        daily_reserved_after = 0

        if not violations:
            try:
                # Ensure budget row exists with current daily_budget_cents from policy
                ensure_budget_row(self.db, agent.id, policy.daily_budget_cents)
                # Atomically reserve the budget
                daily_reserved_before, daily_reserved_after = reserve_budget(
                    self.db, agent.id, amount_cents, policy.daily_budget_cents
                )
            except ValueError as e:
                violations.append(str(e))
                # Get current values for reporting
                usage_date = _get_usage_date()
                existing = self.db.execute(
                    select(DailyBudgetUsage).where(
                        DailyBudgetUsage.agent_id == agent.id,
                        DailyBudgetUsage.usage_date == usage_date,
                    )
                ).scalar_one_or_none()
                if existing:
                    daily_reserved_before = existing.reserved_cents
                    daily_reserved_after = existing.reserved_cents + amount_cents
                else:
                    daily_reserved_before = 0
                    daily_reserved_after = amount_cents

        # Determine decision
        if violations:
            # Hard policy violations always BLOCK
            decision = AuthorizationDecision.BLOCK
            reasons.append("Hard policy violation")
            # Release the reservation since we're not allowing the transaction
            if "exceeded" not in str(violations[-1]).lower():
                # Only release if we actually reserved something
                pass  # The reservation wasn't made if budget check failed
        else:
            # All policy checks passed - budget is reserved
            decision = AuthorizationDecision.ALLOW
            reasons.append("Within policy limits")

        # For backward compatibility, return reserved amounts as "spent"
        return decision, reasons, violations, daily_reserved_before, daily_reserved_after


def record_authorization_decision(
    db: Session,
    request_id: str,
    idempotency_key: Optional[str],
    agent: Agent,
    credential: AgentCredential,
    policy: SpendingPolicy,
    amount_cents: int,
    currency: str,
    merchant_id: str,
    merchant_category: str,
    description: Optional[str],
    decision: AuthorizationDecision,
    reasons: list[str],
    violations: list[str],
    daily_spent_before: int,
    daily_spent_after: int,
    # Risk scoring (Phase 4)
    risk_score: int = 0,
    risk_level: str = "minimal",
    anomaly_signals: Optional[list[dict]] = None,
    anomaly_explanation: Optional[str] = None,
    detection_method: Optional[str] = None,
) -> AuthorizationDecisionRecord:
    """Record an authorization decision for audit trail.

    For ALLOW decisions, also creates an AuthorizationReservation to track
    the budget hold for potential capture/release.

    Does NOT commit - caller must commit the transaction.
    """
    record = AuthorizationDecisionRecord(
        request_id=request_id,
        idempotency_key=idempotency_key,
        agent_id=agent.id,
        credential_id=credential.id,
        policy_id=policy.id,
        amount_cents=amount_cents,
        currency=currency.upper(),
        merchant_id=merchant_id,
        merchant_category=merchant_category,
        description=description,
        decision=decision,
        reasons=json.dumps(reasons),
        policy_violations=json.dumps(violations) if violations else None,
        daily_spent_before_cents=daily_spent_before,
        daily_spent_after_cents=daily_spent_after,
        risk_score=risk_score,
        risk_level=risk_level,
        anomaly_signals=json.dumps(anomaly_signals) if anomaly_signals else None,
        anomaly_explanation=anomaly_explanation,
        detection_method=detection_method,
    )
    db.add(record)
    # No commit - let caller handle transaction
    db.flush()  # Ensure ID is assigned

    # Create reservation only for ALLOW decisions
    # REVIEW decisions require human review and should not reserve budget
    # BLOCK decisions never reserve budget
    if decision == AuthorizationDecision.ALLOW:
        usage_date = _get_usage_date()
        create_reservation(
            db=db,
            auth_decision=record,
            agent_id=agent.id,
            policy_id=policy.id,
            amount_cents=amount_cents,
            currency=currency.upper(),
            usage_date=usage_date,
        )

    return record


def check_idempotency(
    db: Session,
    idempotency_key: str,
    agent_id: int = None,
    amount_cents: int = None,
    currency: str = None,
    merchant_id: str = None,
    merchant_category: str = None,
    description: str = None,
) -> Optional[AuthorizationDecisionRecord]:
    """Check if a request with this idempotency key was already processed.

    If intent parameters are provided, verifies they match the stored record.
    Returns the record if match, None if no record exists.
    Raises ValueError if record exists but intent differs.
    """
    if not idempotency_key:
        return None
    record = db.execute(
        select(AuthorizationDecisionRecord).where(
            AuthorizationDecisionRecord.idempotency_key == idempotency_key
        )
    ).scalar_one_or_none()

    if record is None:
        return None

    # Verify intent matches if parameters provided
    if agent_id is not None and record.agent_id != agent_id:
        raise ValueError("Idempotency key used with different agent")
    if amount_cents is not None and record.amount_cents != amount_cents:
        raise ValueError("Idempotency key used with different amount")
    if currency is not None and record.currency != currency:
        raise ValueError("Idempotency key used with different currency")
    if merchant_id is not None and record.merchant_id != merchant_id:
        raise ValueError("Idempotency key used with different merchant")
    if merchant_category is not None and record.merchant_category != merchant_category:
        raise ValueError("Idempotency key used with different merchant category")
    if description is not None and record.description != description:
        raise ValueError("Idempotency key used with different description")

    return record
