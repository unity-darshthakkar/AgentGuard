"""PayPal Order Orchestration Service.

Internal service that securely binds an authorized AgentGuard reservation
to a PayPal order. This is NOT a public endpoint - it is called by the
payment orchestration layer after authorization verification.

Key security properties:
- Accepts authorization decision ID, NOT arbitrary amount/currency
- Derives amount, currency, and request ID from trusted persisted records
- Verifies decision is ALLOW and reservation is RESERVED
- Rejects expired, released, or captured reservations
- Records attempt BEFORE external call (CREATING status)
- Commits attempt before network call (never holds DB lock across network)
- On timeout: marks UNKNOWN (requires manual reconciliation, no auto-retry)
- On failure: marks FAILED (allows retry with same request_id)
- Reuses existing CREATED binding on repeated requests
- Fail-closed on network uncertainty
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AuthorizationDecisionRecord,
    AuthorizationReservation,
    AuthorizationDecision,
    PayPalOrder,
    PayPalOrderStatus,
    PayPalCapture,
    PayPalCaptureStatus,
    ReservationStatus,
)
from app.services.paypal import (
    PayPalClient,
    PayPalOrderResponse,
    PayPalCaptureResponse,
    PayPalOrderError,
    PayPalCaptureError,
    PayPalAuthenticationError,
    PayPalTimeoutError,
    get_paypal_client,
)


class PayPalOrchestrationError(Exception):
    """Raised when PayPal order orchestration fails."""
    pass


@dataclass
class PayPalOrderBinding:
    """Result of PayPal order orchestration."""
    paypal_order: PayPalOrder
    paypal_response: PayPalOrderResponse
    is_new: bool  # True if newly created, False if reused existing


def _generate_request_id(auth_decision_id: int, reservation_id: int) -> str:
    """Generate a stable, deterministic request ID from authorization and reservation IDs.

    This ensures the same authorization+reservation always produces the same
    PayPal-Request-Id, enabling idempotent retries without storing the ID.
    """
    # Format: "ag-{auth_decision_id}-{reservation_id}"
    # Max length: "ag-" + 10 digits + "-" + 10 digits = 25 chars << 108 limit
    return f"ag-{auth_decision_id}-{reservation_id}"


async def orchestrate_paypal_order(
    db: Session,
    auth_decision_id: int,
    paypal_client: Optional[PayPalClient] = None,
) -> PayPalOrderBinding:
    """
    Orchestrate a PayPal order for an existing authorization decision.

    This function:
    1. Loads the authorization decision and reservation from the database
    2. Verifies the decision is ALLOW
    3. Verifies the reservation is RESERVED and belongs to that decision
    4. Verifies amount and currency match (USD only)
    5. Rejects expired, released, or captured reservations
    6. Derives amount and stable request ID from trusted persisted records
    7. Records a CREATING attempt (or fetches existing) with unique constraint
    8. Commits attempt BEFORE PayPal call (releases DB lock)
    9. Calls PayPal create_order with stable request_id
    10. On success: updates to CREATED with paypal_order_id
    11. On timeout: updates to UNKNOWN, raises PayPalTimeoutError
    12. On other error: updates to FAILED, raises original error

    Args:
        db: Database session
        auth_decision_id: The authorization decision ID to orchestrate
        paypal_client: Optional PayPal client (uses singleton if not provided)

    Returns:
        PayPalOrderBinding with the order, PayPal response, and whether it's new

    Raises:
        PayPalOrchestrationError: If validation fails
        PayPalAuthenticationError: If PayPal auth fails
        PayPalTimeoutError: If PayPal request times out (order marked UNKNOWN)
        PayPalOrderError: If PayPal order creation fails (order marked FAILED)
    """
    # Use singleton client if not provided
    if paypal_client is None:
        paypal_client = get_paypal_client()

    # Load authorization decision with reservation
    auth_decision = db.execute(
        select(AuthorizationDecisionRecord).where(
            AuthorizationDecisionRecord.id == auth_decision_id
        )
    ).scalar_one_or_none()

    if auth_decision is None:
        raise PayPalOrchestrationError(f"Authorization decision {auth_decision_id} not found")

    # Verify decision is ALLOW
    if auth_decision.decision != AuthorizationDecision.ALLOW:
        raise PayPalOrchestrationError(
            f"Cannot create PayPal order for {auth_decision.decision.value} decision. Only ALLOW decisions can be orchestrated."
        )

    # Load reservation
    reservation = db.execute(
        select(AuthorizationReservation).where(
            AuthorizationReservation.auth_decision_id == auth_decision_id
        )
    ).scalar_one_or_none()

    if reservation is None:
        raise PayPalOrchestrationError(f"No reservation found for authorization decision {auth_decision_id}")

    # Verify reservation belongs to this decision
    if reservation.auth_decision_id != auth_decision_id:
        raise PayPalOrchestrationError("Reservation does not match authorization decision")

    # Verify reservation is RESERVED (not released, captured, or expired)
    if reservation.status != ReservationStatus.RESERVED:
        raise PayPalOrchestrationError(
            f"Reservation is {reservation.status.value}, not RESERVED. Cannot create PayPal order."
        )

    # Verify amount and currency match
    if reservation.amount_cents != auth_decision.amount_cents:
        raise PayPalOrchestrationError("Reservation amount does not match authorization decision amount")

    if reservation.currency != auth_decision.currency:
        raise PayPalOrchestrationError("Reservation currency does not match authorization decision currency")

    # Require USD for PayPal
    if reservation.currency != "USD":
        raise PayPalOrchestrationError(f"PayPal orchestration requires USD, got {reservation.currency}")

    # Generate stable request ID from trusted identifiers
    request_id = _generate_request_id(auth_decision_id, reservation.id)

    # Try to insert a CREATING attempt, or fetch existing
    paypal_order, is_new_attempt = await _get_or_create_attempt(db, auth_decision_id, reservation.id, request_id, reservation.amount_cents, reservation.currency)

    # Handle existing attempt based on status
    if not is_new_attempt:
        # We fetched an existing record - check its status
        if paypal_order.status == PayPalOrderStatus.CREATED:
            # Already have a confirmed PayPal order - reuse it
            return PayPalOrderBinding(
                paypal_order=paypal_order,
                paypal_response=PayPalOrderResponse(
                    order_id=paypal_order.paypal_order_id,
                    status=paypal_order.status.value,
                    approval_url=paypal_order.approval_url,
                    payer_id=None,
                    create_time=paypal_order.created_at.isoformat() if paypal_order.created_at else "",
                    update_time=paypal_order.updated_at.isoformat() if paypal_order.updated_at else "",
                    links=[],
                ),
                is_new=False,
            )

        if paypal_order.status == PayPalOrderStatus.CREATING:
            # Another request is in progress - fail fast to avoid duplicate PayPal calls
            raise PayPalOrchestrationError(
                f"PayPal order creation already in progress for authorization decision {auth_decision_id}"
            )

        if paypal_order.status == PayPalOrderStatus.UNKNOWN:
            # Previous attempt timed out - result uncertain, requires manual reconciliation
            # Do NOT auto-retry with same request_id (PayPal idempotency not guaranteed forever)
            raise PayPalOrchestrationError(
                f"Previous PayPal order attempt for authorization decision {auth_decision_id} timed out (status=UNKNOWN). "
                f"Manual reconciliation required before retry."
            )

        # Note: FAILED status is handled atomically in _get_or_create_attempt
        # and returns is_new_attempt=True, so we should not reach here for FAILED

    # At this point, either:
    # - is_new_attempt=True: we created a new CREATING record (or updated from FAILED)
    # - is_new_attempt=False with status=FAILED (handled above, now is_new_attempt=True)
    # Commit the CREATING state BEFORE making the PayPal network call
    # This releases the DB lock so we don't hold a transaction across the network request
    db.commit()

    # Make PayPal call OUTSIDE of database transaction
    try:
        paypal_response = await paypal_client.create_order(
            amount_cents=reservation.amount_cents,
            currency=reservation.currency,
            request_id=request_id,
        )
    except PayPalTimeoutError:
        # Timeout: PayPal may have created the order, result uncertain
        # Update to UNKNOWN and commit
        paypal_order.status = PayPalOrderStatus.UNKNOWN
        db.commit()
        # Re-raise timeout - caller must handle reconciliation manually
        raise
    except (PayPalOrderError, PayPalAuthenticationError) as e:
        # Definitive failure: update to FAILED and commit
        paypal_order.status = PayPalOrderStatus.FAILED
        db.commit()
        # Re-raise original error
        raise

    # Success: update to CREATED with PayPal order details
    paypal_order.paypal_order_id = paypal_response.order_id
    paypal_order.status = PayPalOrderStatus.CREATED
    paypal_order.approval_url = paypal_response.approval_url
    db.commit()
    db.refresh(paypal_order)

    return PayPalOrderBinding(
        paypal_order=paypal_order,
        paypal_response=paypal_response,
        is_new=True,
    )


async def _get_or_create_attempt(
    db: Session,
    auth_decision_id: int,
    reservation_id: int,
    request_id: str,
    amount_cents: int,
    currency: str,
) -> tuple[PayPalOrder, bool]:
    """
    Get existing PayPal order attempt or create new CREATING attempt.

    Uses unique constraint on auth_decision_id to prevent concurrent creation.
    If insert fails due to unique violation, fetches existing record.
    Handles FAILED -> CREATING transition atomically via conditional UPDATE
    to prevent race conditions where two concurrent requests both see FAILED.

    Args:
        db: Database session
        auth_decision_id: Authorization decision ID
        reservation_id: Reservation ID
        request_id: Stable PayPal request ID
        amount_cents: Amount in cents
        currency: Currency code

    Returns:
        Tuple of (PayPalOrder, is_new_attempt)
        - is_new_attempt=True: newly inserted CREATING record (caller should proceed to PayPal call)
        - is_new_attempt=False: fetched existing record (caller must check status)
    """
    # First, try to fetch existing
    existing = db.execute(
        select(PayPalOrder).where(PayPalOrder.auth_decision_id == auth_decision_id)
    ).scalar_one_or_none()

    if existing is not None:
        # Handle FAILED -> CREATING transition atomically via conditional UPDATE
        # This prevents race where two concurrent requests both see FAILED
        if existing.status == PayPalOrderStatus.FAILED:
            # Atomic claim: only proceed if we successfully update from FAILED to CREATING
            # The WHERE clause ensures only one concurrent request can claim this transition
            from sqlalchemy import update
            result = db.execute(
                update(PayPalOrder)
                .where(PayPalOrder.id == existing.id)
                .where(PayPalOrder.status == PayPalOrderStatus.FAILED)
                .values(status=PayPalOrderStatus.CREATING)
            )
            if result.rowcount == 1:
                db.commit()
                # Reload the claimed record
                claimed = db.execute(
                    select(PayPalOrder).where(PayPalOrder.id == existing.id)
                ).scalar_one()
                return claimed, True  # We won the claim, proceed to PayPal call
            else:
                # Lost the race - another request claimed the FAILED -> CREATING transition
                db.rollback()
                # Reload and return existing (will be CREATING or CREATED)
                reloaded = db.execute(
                    select(PayPalOrder).where(PayPalOrder.auth_decision_id == auth_decision_id)
                ).scalar_one()
                return reloaded, False
        return existing, False

    # No existing - try to insert CREATING attempt
    new_order = PayPalOrder(
        auth_decision_id=auth_decision_id,
        reservation_id=reservation_id,
        paypal_order_id=None,  # NULL during CREATING
        paypal_request_id=request_id,
        amount_cents=amount_cents,
        currency=currency,
        status=PayPalOrderStatus.CREATING,
        approval_url=None,
    )
    db.add(new_order)
    try:
        db.commit()
        db.refresh(new_order)
        return new_order, True
    except IntegrityError:
        # Concurrent insert won - rollback and fetch the winner
        db.rollback()
        winner = db.execute(
            select(PayPalOrder).where(PayPalOrder.auth_decision_id == auth_decision_id)
        ).scalar_one()
        # If winner is FAILED, atomically transition to CREATING
        if winner.status == PayPalOrderStatus.FAILED:
            from sqlalchemy import update
            result = db.execute(
                update(PayPalOrder)
                .where(PayPalOrder.id == winner.id)
                .where(PayPalOrder.status == PayPalOrderStatus.FAILED)
                .values(status=PayPalOrderStatus.CREATING)
            )
            if result.rowcount == 1:
                db.commit()
                claimed = db.execute(
                    select(PayPalOrder).where(PayPalOrder.id == winner.id)
                ).scalar_one()
                return claimed, True
            else:
                db.rollback()
                reloaded = db.execute(
                    select(PayPalOrder).where(PayPalOrder.auth_decision_id == auth_decision_id)
                ).scalar_one()
                return reloaded, False
        return winner, False


async def get_paypal_order_binding(
    db: Session,
    auth_decision_id: int,
) -> Optional[PayPalOrderBinding]:
    """
    Get existing PayPal order binding for an authorization decision.

    Args:
        db: Database session
        auth_decision_id: The authorization decision ID

    Returns:
        PayPalOrderBinding if exists, None otherwise
    """
    paypal_order = db.execute(
        select(PayPalOrder).where(
            PayPalOrder.auth_decision_id == auth_decision_id
        )
    ).scalar_one_or_none()

    if paypal_order is None:
        return None

    # Only return binding for CREATED orders (not CREATING/UNKNOWN/FAILED)
    if paypal_order.status != PayPalOrderStatus.CREATED:
        return None

    return PayPalOrderBinding(
        paypal_order=paypal_order,
        paypal_response=PayPalOrderResponse(
            order_id=paypal_order.paypal_order_id,
            status=paypal_order.status.value,
            approval_url=paypal_order.approval_url,
            payer_id=None,
            create_time=paypal_order.created_at.isoformat() if paypal_order.created_at else "",
            update_time=paypal_order.updated_at.isoformat() if paypal_order.updated_at else "",
            links=[],
        ),
        is_new=False,
    )


@dataclass
class PayPalCaptureBinding:
    """Result of PayPal capture orchestration."""
    paypal_capture: PayPalCapture
    paypal_response: PayPalCaptureResponse
    is_new: bool  # True if newly captured, False if reused existing


def _generate_capture_request_id(auth_decision_id: int, reservation_id: int) -> str:
    """Generate a stable, deterministic capture request ID.

    Distinct from the create-order request ID to avoid cross-API idempotency conflicts.
    Format: "ag-cap-{auth_decision_id}-{reservation_id}"
    """
    return f"ag-cap-{auth_decision_id}-{reservation_id}"


async def orchestrate_paypal_capture(
    db: Session,
    auth_decision_id: int,
    paypal_client: Optional[PayPalClient] = None,
) -> PayPalCaptureBinding:
    """
    Orchestrate a PayPal capture for an existing confirmed PayPal order.

    This function:
    1. Loads the PayPal order, authorization decision, and reservation
    2. Verifies the decision is ALLOW
    3. Verifies the PayPal order is CREATED (not CREATING/UNKNOWN/FAILED)
    4. Verifies the reservation is RESERVED and belongs to that decision
    5. Verifies amount and currency match exactly
    6. Checks PayPal order status is buyer-approved (COMPLETED/APPROVED)
    7. Records a CAPTURING attempt (or fetches existing) with unique constraint
    8. Commits attempt BEFORE PayPal call (releases DB lock)
    9. Calls PayPal capture_order with stable capture-specific request_id
    10. On success: verifies capture COMPLETED, amount/currency match, updates to COMPLETED
    11. On success: transitions reservation to CAPTURED, updates daily budget
    12. On timeout: updates to UNKNOWN, raises PayPalTimeoutError
    13. On other error: updates to FAILED, raises original error

    Args:
        db: Database session
        auth_decision_id: The authorization decision ID to capture
        paypal_client: Optional PayPal client (uses singleton if not provided)

    Returns:
        PayPalCaptureBinding with the capture, PayPal response, and whether it's new

    Raises:
        PayPalOrchestrationError: If validation fails (wrong status, amount mismatch, etc.)
        PayPalAuthenticationError: If PayPal auth fails
        PayPalTimeoutError: If PayPal request times out (capture marked UNKNOWN)
        PayPalCaptureError: If PayPal capture fails (capture marked FAILED)
    """
    # Use singleton client if not provided
    if paypal_client is None:
        paypal_client = get_paypal_client()

    # Load authorization decision
    auth_decision = db.execute(
        select(AuthorizationDecisionRecord).where(
            AuthorizationDecisionRecord.id == auth_decision_id
        )
    ).scalar_one_or_none()

    if auth_decision is None:
        raise PayPalOrchestrationError(f"Authorization decision {auth_decision_id} not found")

    # Verify decision is ALLOW
    if auth_decision.decision != AuthorizationDecision.ALLOW:
        raise PayPalOrchestrationError(
            f"Cannot capture for {auth_decision.decision.value} decision. Only ALLOW decisions can be captured."
        )

    # Load PayPal order
    paypal_order = db.execute(
        select(PayPalOrder).where(PayPalOrder.auth_decision_id == auth_decision_id)
    ).scalar_one_or_none()

    if paypal_order is None:
        raise PayPalOrchestrationError(f"No PayPal order found for authorization decision {auth_decision_id}")

    # Verify PayPal order is CREATED (not CREATING/UNKNOWN/FAILED)
    if paypal_order.status != PayPalOrderStatus.CREATED:
        raise PayPalOrchestrationError(
            f"PayPal order status is {paypal_order.status.value}, not CREATED. Cannot capture."
        )

    if not paypal_order.paypal_order_id:
        raise PayPalOrchestrationError("PayPal order ID is missing (not confirmed)")

    # Load reservation
    reservation = db.execute(
        select(AuthorizationReservation).where(
            AuthorizationReservation.auth_decision_id == auth_decision_id
        )
    ).scalar_one_or_none()

    if reservation is None:
        raise PayPalOrchestrationError(f"No reservation found for authorization decision {auth_decision_id}")

    # Verify reservation belongs to this decision
    if reservation.auth_decision_id != auth_decision_id:
        raise PayPalOrchestrationError("Reservation does not match authorization decision")

    # Verify amount and currency match exactly
    if reservation.amount_cents != auth_decision.amount_cents:
        raise PayPalOrchestrationError("Reservation amount does not match authorization decision amount")

    if reservation.currency != auth_decision.currency:
        raise PayPalOrchestrationError("Reservation currency does not match authorization decision currency")

    if reservation.amount_cents != paypal_order.amount_cents:
        raise PayPalOrchestrationError("PayPal order amount does not match reservation amount")

    if reservation.currency != paypal_order.currency:
        raise PayPalOrchestrationError("PayPal order currency does not match reservation currency")

    # Require USD for PayPal
    if reservation.currency != "USD":
        raise PayPalOrchestrationError(f"PayPal orchestration requires USD, got {reservation.currency}")

    # Check PayPal order status is buyer-approved before capturing
    # We need to call GET /v2/checkout/orders/{id} to verify buyer approval
    try:
        order_details = await paypal_client.get(f"/v2/checkout/orders/{paypal_order.paypal_order_id}")
    except PayPalTimeoutError:
        raise PayPalOrchestrationError("Timed out checking PayPal order status")
    except (PayPalOrderError, PayPalAuthenticationError) as e:
        raise PayPalOrchestrationError(f"Failed to check PayPal order status: {e}")

    order_status = order_details.get("status")
    if order_status not in ("COMPLETED", "APPROVED"):
        raise PayPalOrchestrationError(
            f"PayPal order not approved by buyer (status: {order_status}). Cannot capture."
        )

    # Generate stable capture request ID (distinct from create-order request ID)
    capture_request_id = _generate_capture_request_id(auth_decision_id, reservation.id)

    # Try to insert a CAPTURING attempt, or fetch existing
    paypal_capture, is_new_attempt = await _get_or_create_capture_attempt(
        db, paypal_order.id, capture_request_id, reservation.amount_cents, reservation.currency
    )

    # Handle existing attempt based on status
    if not is_new_attempt:
        if paypal_capture.status == PayPalCaptureStatus.COMPLETED:
            # Already captured - verify reservation is CAPTURED (idempotent re-call)
            # If reservation is still RESERVED, it's an inconsistent state - fail closed
            if reservation.status == ReservationStatus.CAPTURED:
                return PayPalCaptureBinding(
                    paypal_capture=paypal_capture,
                    paypal_response=PayPalCaptureResponse(
                        capture_id=paypal_capture.paypal_capture_id or "",
                        capture_status=paypal_capture.status.value,
                        order_id=paypal_order.paypal_order_id,
                        order_status=order_status,
                        currency=paypal_capture.currency,
                        amount_cents=paypal_capture.amount_cents,
                        create_time=paypal_capture.created_at.isoformat() if paypal_capture.created_at else "",
                        update_time=paypal_capture.updated_at.isoformat() if paypal_capture.updated_at else "",
                        links=[],
                    ),
                    is_new=False,
                )
            else:
                raise PayPalOrchestrationError(
                    f"Inconsistent state: capture is COMPLETED but reservation is {reservation.status.value}. "
                    f"Manual reconciliation required."
                )

        if paypal_capture.status == PayPalCaptureStatus.CAPTURING:
            raise PayPalOrchestrationError(
                f"PayPal capture already in progress for authorization decision {auth_decision_id}"
            )

        if paypal_capture.status == PayPalCaptureStatus.UNKNOWN:
            raise PayPalOrchestrationError(
                f"Previous PayPal capture attempt for authorization decision {auth_decision_id} timed out (status=UNKNOWN). "
                f"Manual reconciliation required before retry."
            )

        # FAILED status is handled atomically in _get_or_create_capture_attempt

    # For NEW attempts, reservation MUST be RESERVED
    if reservation.status != ReservationStatus.RESERVED:
        raise PayPalOrchestrationError(
            f"Reservation is {reservation.status.value}, not RESERVED. Cannot capture."
        )

    # Commit CAPTURING state BEFORE making PayPal network call
    db.commit()

    # Make PayPal capture call OUTSIDE of database transaction
    try:
        paypal_response = await paypal_client.capture_order(
            order_id=paypal_order.paypal_order_id,
            request_id=capture_request_id,
        )
    except PayPalTimeoutError:
        # Timeout: PayPal may have captured, result uncertain
        paypal_capture.status = PayPalCaptureStatus.UNKNOWN
        db.commit()
        raise
    except (PayPalCaptureError, PayPalAuthenticationError) as e:
        # Definitive failure: update to FAILED and commit
        paypal_capture.status = PayPalCaptureStatus.FAILED
        db.commit()
        raise

    # Verify PayPal response matches our expectations exactly
    # capture_order already validates COMPLETED status, USD currency, exact amount
    # But we double-check the amounts match the reservation
    if paypal_response.amount_cents != reservation.amount_cents:
        # Amount mismatch: PayPal may have captured funds - mark as UNKNOWN for reconciliation
        paypal_capture.paypal_capture_id = paypal_response.capture_id
        paypal_capture.status = PayPalCaptureStatus.UNKNOWN
        paypal_capture.completed_at = datetime.utcnow()
        db.commit()
        raise PayPalOrchestrationError(
            f"Captured amount {paypal_response.amount_cents} cents does not match reservation "
            f"{reservation.amount_cents} cents. Capture recorded but amounts diverge. "
            f"Manual reconciliation required."
        )

    if paypal_response.currency != reservation.currency:
        # Currency mismatch: PayPal may have captured funds - mark as UNKNOWN for reconciliation
        paypal_capture.paypal_capture_id = paypal_response.capture_id
        paypal_capture.status = PayPalCaptureStatus.UNKNOWN
        paypal_capture.completed_at = datetime.utcnow()
        db.commit()
        raise PayPalOrchestrationError(
            f"Captured currency {paypal_response.currency} does not match reservation "
            f"{reservation.currency}. Capture recorded but currencies diverge. "
            f"Manual reconciliation required."
        )

    # Success: update capture to COMPLETED with PayPal capture details
    paypal_capture.paypal_capture_id = paypal_response.capture_id
    paypal_capture.status = PayPalCaptureStatus.COMPLETED
    paypal_capture.completed_at = datetime.utcnow()

    # Transition reservation to CAPTURED and update daily budget
    # Use the auth service's capture_reservation function
    from app.services.auth import capture_reservation
    budget_ok = capture_reservation(
        db=db,
        auth_decision_id=auth_decision_id,
        agent_id=auth_decision.agent_id,
        amount_cents=reservation.amount_cents,
    )

    if not budget_ok:
        # This should not happen if our validation passed, but fail closed
        # Preserve capture evidence, leave transaction flagged for reconciliation
        # Mark capture as UNKNOWN to prevent auto-retry
        paypal_capture.status = PayPalCaptureStatus.UNKNOWN
        db.commit()
        raise PayPalOrchestrationError(
            "Budget update failed during capture - reservation may already be captured or released. "
            "Manual reconciliation required."
        )

    # Atomic commit: capture COMPLETED + reservation CAPTURED + budget updated
    db.commit()
    db.refresh(paypal_capture)

    return PayPalCaptureBinding(
        paypal_capture=paypal_capture,
        paypal_response=paypal_response,
        is_new=True,
    )


async def _get_or_create_capture_attempt(
    db: Session,
    paypal_order_id: int,
    request_id: str,
    amount_cents: int,
    currency: str,
) -> tuple[PayPalCapture, bool]:
    """
    Get existing PayPal capture attempt or create new CAPTURING attempt.

    Uses unique constraint on paypal_order_id to prevent concurrent capture.
    If insert fails due to unique violation, fetches existing record.
    Handles FAILED -> CAPTURING transition atomically via conditional UPDATE
    to prevent race conditions where two concurrent requests both see FAILED.

    Args:
        db: Database session
        paypal_order_id: PayPal order ID (FK to paypal_orders)
        request_id: Stable PayPal-Request-Id for capture call
        amount_cents: Amount in cents
        currency: Currency code

    Returns:
        Tuple of (PayPalCapture, is_new_attempt)
        - is_new_attempt=True: newly inserted CAPTURING record (caller should proceed to PayPal call)
        - is_new_attempt=False: fetched existing record (caller must check status)
    """
    # First, try to fetch existing
    existing = db.execute(
        select(PayPalCapture).where(PayPalCapture.paypal_order_id == paypal_order_id)
    ).scalar_one_or_none()

    if existing is not None:
        # Handle FAILED -> CAPTURING transition atomically via conditional UPDATE
        if existing.status == PayPalCaptureStatus.FAILED:
            result = db.execute(
                update(PayPalCapture)
                .where(PayPalCapture.id == existing.id)
                .where(PayPalCapture.status == PayPalCaptureStatus.FAILED)
                .values(status=PayPalCaptureStatus.CAPTURING)
            )
            if result.rowcount == 1:
                db.commit()
                claimed = db.execute(
                    select(PayPalCapture).where(PayPalCapture.id == existing.id)
                ).scalar_one()
                return claimed, True
            else:
                db.rollback()
                reloaded = db.execute(
                    select(PayPalCapture).where(PayPalCapture.paypal_order_id == paypal_order_id)
                ).scalar_one()
                return reloaded, False
        return existing, False

    # No existing - try to insert CAPTURING attempt
    new_capture = PayPalCapture(
        paypal_order_id=paypal_order_id,
        paypal_capture_id=None,  # NULL during CAPTURING
        paypal_request_id=request_id,
        amount_cents=amount_cents,
        currency=currency,
        status=PayPalCaptureStatus.CAPTURING,
    )
    db.add(new_capture)
    try:
        db.commit()
        db.refresh(new_capture)
        return new_capture, True
    except IntegrityError:
        # Concurrent insert won - rollback and fetch the winner
        db.rollback()
        winner = db.execute(
            select(PayPalCapture).where(PayPalCapture.paypal_order_id == paypal_order_id)
        ).scalar_one()
        # If winner is FAILED, atomically transition to CAPTURING
        if winner.status == PayPalCaptureStatus.FAILED:
            result = db.execute(
                update(PayPalCapture)
                .where(PayPalCapture.id == winner.id)
                .where(PayPalCapture.status == PayPalCaptureStatus.FAILED)
                .values(status=PayPalCaptureStatus.CAPTURING)
            )
            if result.rowcount == 1:
                db.commit()
                claimed = db.execute(
                    select(PayPalCapture).where(PayPalCapture.id == winner.id)
                ).scalar_one()
                return claimed, True
            else:
                db.rollback()
                reloaded = db.execute(
                    select(PayPalCapture).where(PayPalCapture.paypal_order_id == paypal_order_id)
                ).scalar_one()
                return reloaded, False
        return winner, False