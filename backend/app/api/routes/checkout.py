"""PayPal Sandbox Checkout API endpoints.

Secure endpoints for starting and checking the status of PayPal sandbox checkout
for already-authorized AgentGuard payment decisions.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.auth_deps import get_checkout_requester, verify_admin_api_key
from app.core.database import get_db
from app.models import (
    Agent,
    AuthorizationDecision,
    AuthorizationDecisionRecord,
    AuthorizationReservation,
    PayPalCapture,
    PayPalCaptureStatus,
    PayPalOrder,
    PayPalOrderStatus,
    ReservationStatus,
)
from app.schemas import (
    CheckoutStartRequest,
    CheckoutStartResponse,
    CheckoutStatusResponse,
    CheckoutCaptureResponse,
)
from app.services.paypal_orchestration import (
    orchestrate_paypal_order,
    orchestrate_paypal_capture,
    get_paypal_order_binding,
    PayPalOrchestrationError,
)
from app.services.paypal import get_paypal_client, PayPalTimeoutError

router = APIRouter(prefix="/checkout", tags=["checkout"])


def _map_paypal_order_status_to_checkout(order_status: Optional[PayPalOrderStatus]) -> str:
    """Map PayPal order orchestration status to checkout status."""
    if order_status is None:
        return "pending_approval"
    mapping = {
        PayPalOrderStatus.CREATING: "pending_approval",
        PayPalOrderStatus.CREATED: "created",
        PayPalOrderStatus.UNKNOWN: "timeout",
        PayPalOrderStatus.FAILED: "failed",
    }
    return mapping.get(order_status, "unknown")


def _map_reservation_status(status: Optional[ReservationStatus]) -> str:
    """Map reservation status enum to string."""
    if status is None:
        return "unknown"
    return status.value


def _map_paypal_capture_status(status: Optional[PayPalCaptureStatus]) -> Optional[str]:
    """Map PayPal capture status enum to string."""
    if status is None:
        return None
    return status.value


@router.post(
    "/{authorization_decision_id}/capture",
    response_model=CheckoutCaptureResponse,
    summary="Capture PayPal order after buyer approval",
    dependencies=[Depends(verify_admin_api_key)],
)
async def capture_checkout(
    authorization_decision_id: int,
    db: Session = Depends(get_db),
    admin_id: str = Depends(verify_admin_api_key),
) -> CheckoutCaptureResponse:
    """
    Capture a PayPal order after buyer has approved it in the sandbox.

    This endpoint:
    1. Validates the authorization decision exists and is ALLOW
    2. Verifies the PayPal order exists and is CREATED (buyer-approved)
    3. Verifies the reservation is RESERVED and belongs to the decision
    4. Invokes orchestrate_paypal_capture() to capture the PayPal order
    5. Returns PayPal capture ID, capture status, and reservation status

    Security:
    - Requires admin authentication (X-Admin-API-Key header)
    - Only accepts authorization_decision_id - no arbitrary amounts/currencies
    - Verifies agent ownership and decision/reservation binding
    - Rejects BLOCK/REVIEW decisions
    - Rejects released/expired/captured reservations
    - Rejects unapproved PayPal orders (CREATING/UNKNOWN/FAILED)
    - Blocks UNKNOWN/unsafe payment attempts
    - Never exposes PayPal client secrets or access tokens

    Idempotency:
    - Repeated calls with same authorization_decision_id return the SAME capture
    - Uses stable PayPal-Request-Id derived from auth_decision_id + reservation_id
    - COMPLETED captures are idempotent; FAILED attempts can be retried
    - UNKNOWN requires manual reconciliation (no auto-retry)
    """
    # Load authorization decision
    auth_decision = db.query(AuthorizationDecisionRecord).filter(
        AuthorizationDecisionRecord.id == authorization_decision_id
    ).first()

    if not auth_decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Authorization decision {authorization_decision_id} not found",
        )

    # Verify decision is ALLOW
    if auth_decision.decision != AuthorizationDecision.ALLOW:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot capture for {auth_decision.decision.value} decision. Only ALLOW decisions can be captured.",
        )

    # Load PayPal order
    paypal_order = db.query(PayPalOrder).filter(
        PayPalOrder.auth_decision_id == authorization_decision_id
    ).first()

    if not paypal_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No PayPal order found for authorization decision {authorization_decision_id}",
        )

    # Verify PayPal order is CREATED (not CREATING/UNKNOWN/FAILED)
    if paypal_order.status != PayPalOrderStatus.CREATED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"PayPal order status is {paypal_order.status.value}, not CREATED. Cannot capture.",
        )

    if not paypal_order.paypal_order_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PayPal order ID is missing (not confirmed). Cannot capture.",
        )

    # Load reservation
    reservation = db.query(AuthorizationReservation).filter(
        AuthorizationReservation.auth_decision_id == authorization_decision_id
    ).first()

    if not reservation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No reservation found for authorization decision {authorization_decision_id}",
        )

    # Verify reservation belongs to this decision
    if reservation.auth_decision_id != authorization_decision_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation does not match authorization decision",
        )

    # Verify reservation is not RELEASED or EXPIRED (these are invalid for capture)
    # CAPTURED is allowed to proceed for idempotency (orchestration handles it)
    if reservation.status in (ReservationStatus.RELEASED, ReservationStatus.EXPIRED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Reservation is {reservation.status.value}, not RESERVED. Cannot capture.",
        )

    # Verify amount and currency match
    if reservation.amount_cents != auth_decision.amount_cents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation amount does not match authorization decision amount",
        )

    if reservation.currency != auth_decision.currency:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation currency does not match authorization decision currency",
        )

    # Require USD for PayPal
    if reservation.currency != "USD":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PayPal capture requires USD, got {reservation.currency}",
        )

    # Load agent for verification
    agent = db.query(Agent).filter(Agent.id == auth_decision.agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent for authorization decision not found",
        )

    # Invoke PayPal capture orchestration
    try:
        paypal_client = get_paypal_client()
        binding = await orchestrate_paypal_capture(db, authorization_decision_id, paypal_client)
    except PayPalOrchestrationError as e:
        # Check if it's a "buyer not approved" error - return 409
        if "not approved" in str(e).lower() or "buyer" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e),
            )
        # Check for inconsistent state (capture COMPLETED but reservation not CAPTURED)
        if "inconsistent state" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e),
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except PayPalTimeoutError:
        # Timeout during PayPal call - capture status is UNKNOWN
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="PayPal capture timed out. Result uncertain - manual reconciliation required.",
        )

    # Re-read reservation from database after orchestration to get updated status
    # The orchestration layer updates the reservation to CAPTURED on success
    db.refresh(reservation)

    paypal_capture = binding.paypal_capture
    capture_status = _map_paypal_capture_status(paypal_capture.status)

    # Determine reconciliation requirements
    reconciliation_required = False
    reconciliation_reason = None

    if paypal_capture.status == PayPalCaptureStatus.UNKNOWN:
        reconciliation_required = True
        reconciliation_reason = "PayPal capture timed out - result uncertain"
    elif paypal_capture.status == PayPalCaptureStatus.FAILED:
        if paypal_capture.paypal_capture_id:
            reconciliation_required = True
            reconciliation_reason = "PayPal capture completed but amount/currency mismatch detected"

    return CheckoutCaptureResponse(
        authorization_decision_id=authorization_decision_id,
        reservation_id=reservation.id,
        paypal_order_id=paypal_order.paypal_order_id,
        paypal_capture_id=paypal_capture.paypal_capture_id,
        capture_status=capture_status,
        reservation_status=_map_reservation_status(reservation.status),
        reconciliation_required=reconciliation_required,
        reconciliation_reason=reconciliation_reason,
        message="PayPal order captured successfully. Reservation marked CAPTURED and budget updated." if binding.is_new
                else "Existing PayPal capture reused. Reservation already CAPTURED.",
    )


@router.post(
    "/start",
    response_model=CheckoutStartResponse,
    summary="Start PayPal sandbox checkout for an authorized decision",
    dependencies=[Depends(verify_admin_api_key)],
)
async def start_checkout(
    request: CheckoutStartRequest,
    db: Session = Depends(get_db),
    admin_id: str = Depends(verify_admin_api_key),
) -> CheckoutStartResponse:
    """
    Start PayPal sandbox checkout for an already-authorized payment decision.

    This endpoint:
    1. Validates the authorization decision exists and is ALLOW
    2. Verifies the reservation is RESERVED and belongs to the decision
    3. Invokes orchestrate_paypal_order() to create/reuse PayPal order
    4. Returns PayPal order ID, approval URL, and checkout status

    Security:
    - Requires admin authentication (X-Admin-API-Key header)
    - Only accepts authorization_decision_id - no arbitrary amounts/currencies
    - Verifies agent ownership and decision/reservation binding
    - Rejects BLOCK/REVIEW decisions, released/expired/captured reservations
    - Blocks UNKNOWN/unsafe payment attempts
    - Never exposes PayPal client secrets or access tokens

    Idempotency:
    - Repeated calls with same authorization_decision_id return the SAME PayPal order
    - Uses stable PayPal-Request-Id derived from auth_decision_id + reservation_id
    - FAILED attempts can be retried; UNKNOWN requires manual reconciliation
    """
    # Load authorization decision
    auth_decision = db.query(AuthorizationDecisionRecord).filter(
        AuthorizationDecisionRecord.id == request.authorization_decision_id
    ).first()

    if not auth_decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Authorization decision {request.authorization_decision_id} not found",
        )

    # Verify decision is ALLOW
    if auth_decision.decision != AuthorizationDecision.ALLOW:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot start checkout for {auth_decision.decision.value} decision. Only ALLOW decisions can proceed to PayPal.",
        )

    # Load reservation
    reservation = db.query(AuthorizationReservation).filter(
        AuthorizationReservation.auth_decision_id == request.authorization_decision_id
    ).first()

    if not reservation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No reservation found for authorization decision {request.authorization_decision_id}",
        )

    # Verify reservation belongs to this decision
    if reservation.auth_decision_id != request.authorization_decision_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation does not match authorization decision",
        )

    # Verify reservation is RESERVED (not released, captured, or expired)
    if reservation.status != ReservationStatus.RESERVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Reservation is {reservation.status.value}, not RESERVED. Cannot start checkout.",
        )

    # Verify amount and currency match
    if reservation.amount_cents != auth_decision.amount_cents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation amount does not match authorization decision amount",
        )

    if reservation.currency != auth_decision.currency:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation currency does not match authorization decision currency",
        )

    # Require USD for PayPal
    if reservation.currency != "USD":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PayPal checkout requires USD, got {reservation.currency}",
        )

    # Load agent for verification
    agent = db.query(Agent).filter(Agent.id == auth_decision.agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent for authorization decision not found",
        )

    # Invoke PayPal order orchestration
    try:
        paypal_client = get_paypal_client()
        binding = await orchestrate_paypal_order(db, request.authorization_decision_id, paypal_client)
    except PayPalOrchestrationError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except PayPalTimeoutError:
        # Timeout during PayPal call - order status is UNKNOWN
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="PayPal order creation timed out. Result uncertain - manual reconciliation required.",
        )

    paypal_order = binding.paypal_order
    checkout_status = _map_paypal_order_status_to_checkout(paypal_order.status)

    return CheckoutStartResponse(
        authorization_decision_id=request.authorization_decision_id,
        reservation_id=reservation.id,
        paypal_order_id=paypal_order.paypal_order_id,
        approval_url=paypal_order.approval_url or "",
        checkout_status=checkout_status,
        reservation_status=_map_reservation_status(reservation.status),
        message="PayPal order created successfully. Redirect buyer to approval_url." if binding.is_new
                else "Existing PayPal order reused. Redirect buyer to approval_url.",
    )


@router.get(
    "/{authorization_decision_id}",
    response_model=CheckoutStatusResponse,
    summary="Get checkout status for an authorization decision",
)
async def get_checkout_status(
    authorization_decision_id: int,
    request: Request,
    db: Session = Depends(get_db),
    requester: tuple = Depends(get_checkout_requester),
) -> CheckoutStatusResponse:
    """
    Get checkout status for an authorization decision.

    Returns sanitized status information including:
    - Authorization decision details
    - Reservation status
    - PayPal order status (if any)
    - PayPal capture status (if any)
    - Approval URL (if applicable)
    - Reconciliation-required flag

    Security:
    - No sensitive credentials exposed
    - No automatic PayPal retry
    - Read-only database access

    Authorization:
    - Requires authentication: either admin (X-Admin-API-Key) or agent (Ed25519 signed request)
    - Admin can access any authorization decision
    - Agent can only access their own authorization decisions
    - Unauthenticated requests are rejected with 401
    """
    requester_type, agent, credential = requester

    # Check authentication
    if requester_type is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide either X-Admin-API-Key header or agent authentication headers (X-Agent-Id, X-Key-Id, X-Nonce, X-Timestamp, X-Signature)",
        )

    # Load authorization decision
    auth_decision = db.query(AuthorizationDecisionRecord).filter(
        AuthorizationDecisionRecord.id == authorization_decision_id
    ).first()

    if not auth_decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Authorization decision {authorization_decision_id} not found",
        )

    # For agent access, verify ownership (already verified in dependency, but double-check)
    if requester_type == "agent" and auth_decision.agent_id != agent.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this authorization decision",
        )

    # Load reservation
    reservation = db.query(AuthorizationReservation).filter(
        AuthorizationReservation.auth_decision_id == authorization_decision_id
    ).first()

    if not reservation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No reservation found for authorization decision {authorization_decision_id}",
        )

    # Load PayPal order if exists
    paypal_order = db.query(PayPalOrder).filter(
        PayPalOrder.auth_decision_id == authorization_decision_id
    ).first()

    # Load PayPal capture if exists
    paypal_capture = None
    if paypal_order:
        paypal_capture = db.query(PayPalCapture).filter(
            PayPalCapture.paypal_order_id == paypal_order.id
        ).first()

    # Determine reconciliation requirements
    reconciliation_required = False
    reconciliation_reason = None

    if paypal_order and paypal_order.status == PayPalOrderStatus.UNKNOWN:
        reconciliation_required = True
        reconciliation_reason = "PayPal order creation timed out - result uncertain"
    elif paypal_capture and paypal_capture.status == PayPalCaptureStatus.UNKNOWN:
        reconciliation_required = True
        reconciliation_reason = "PayPal capture timed out - result uncertain"
    elif paypal_capture and paypal_capture.status == PayPalCaptureStatus.FAILED:
        # Check if amount/currency mismatch caused the failure
        if paypal_capture.paypal_capture_id:
            reconciliation_required = True
            reconciliation_reason = "PayPal capture completed but amount/currency mismatch detected"

    # Build response
    response = CheckoutStatusResponse(
        authorization_decision_id=authorization_decision_id,
        request_id=auth_decision.request_id,
        agent_id=auth_decision.agent_id,
        amount_cents=auth_decision.amount_cents,
        currency=auth_decision.currency,
        merchant_id=auth_decision.merchant_id,
        merchant_category=auth_decision.merchant_category,
        description=auth_decision.description,
        decision=auth_decision.decision.value,
        reservation_status=_map_reservation_status(reservation.status),
        paypal_order_status=_map_paypal_order_status_to_checkout(paypal_order.status) if paypal_order else None,
        paypal_order_id=paypal_order.paypal_order_id if paypal_order else None,
        approval_url=paypal_order.approval_url if paypal_order else None,
        paypal_capture_status=_map_paypal_capture_status(paypal_capture.status) if paypal_capture else None,
        paypal_capture_id=paypal_capture.paypal_capture_id if paypal_capture else None,
        reconciliation_required=reconciliation_required,
        reconciliation_reason=reconciliation_reason,
        decided_at=auth_decision.decided_at,
        reserved_at=reservation.reserved_at,
        captured_at=reservation.captured_at,
    )

    return response