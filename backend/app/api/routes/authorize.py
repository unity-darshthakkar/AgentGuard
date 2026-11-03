"""Payment authorization API endpoints."""

import json
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Agent, AgentCredential, AgentStatus, AuthorizationDecision, SpendingPolicy, DailyBudgetUsage, AuthorizationDecisionRecord, AuthorizationReservation, ReservationStatus
from app.schemas import (
    AuthorizationRequest,
    AuthorizationResponse,
    AuthorizationDecisionResponse,
    AuthorizationDecisionListResponse,
    AuthorizationReservationResponse,
    AuthorizationReservationListResponse,
    ReservationCaptureRequest,
    ReservationReleaseRequest,
    ReservationExpireRequest,
    ReservationLifecycleResponse,
    PaginationParams,
)
from app.core.auth_deps import verify_admin_api_key
from app.services import (
    get_active_credential,
    check_credential_valid,
    get_active_policy,
    consume_nonce,
    verify_signature,
    load_public_key,
    canonical_request_string,
    compute_body_hash,
    AuthorizationService,
    record_authorization_decision,
    check_idempotency,
    capture_reservation,
    release_reservation,
    expire_reservation,
    get_reservation_by_auth_decision,
    expire_old_reservations,
)
from app.services.auth import _get_usage_date
from app.services.anomaly_detection import AnomalyDetectionService, normalize_risk_score

router = APIRouter(prefix="/authorize", tags=["authorization"])


# =============================================================================
# Authorization Endpoint
# =============================================================================


@router.post(
    "",
    response_model=AuthorizationResponse,
    summary="Evaluate payment authorization request",
)
async def authorize_payment(
    request: AuthorizationRequest,
    http_request: Request,
    db: Session = Depends(get_db),
) -> AuthorizationResponse:
    """
    Evaluate a payment authorization request from an authenticated agent.

    This is the core authorization endpoint that agents call before initiating payments.
    The request must be signed with the agent's Ed25519 private key.

    Authorization flow:
    1. Agent gets nonce from `/auth/challenge`
    2. Agent creates payment intent and signs it with private key
    3. Agent sends signed request to this endpoint
    4. Server verifies signature, nonce, timestamp, and policy
    5. Returns ALLOW, BLOCK, or REVIEW with reasons

    Security features:
    - Ed25519 signature verification
    - Replay protection via single-use nonces
    - Timestamp validation (±2 minutes)
    - Policy enforcement (limits, currencies, merchants, budget)
    - Idempotency key support
    - Full audit trail

    Returns:
    - **ALLOW**: Payment can proceed to PayPal (Phase 3)
    - **BLOCK**: Hard policy violation, payment rejected
    - **REVIEW**: Requires human review (future AI risk integration)
    """
    # 1. Verify agent exists
    agent = db.query(Agent).filter(Agent.agent_id == request.agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{request.agent_id}' not found",
        )

    # Check agent status - reject suspended/pending_review/decommissioned
    if agent.status != AgentStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Agent is {agent.status.value}. Only active agents can request authorization.",
        )

    # 2. Verify credential exists and is active
    credential = get_active_credential(db, agent.id, request.key_id)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive credential",
        )

    is_valid, message = check_credential_valid(credential)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Credential invalid: {message}",
        )

    # 3. Verify timestamp (prevent stale requests)
    request_time = request.timestamp
    now = datetime.utcnow()
    if abs((now - request_time).total_seconds()) > 120:  # 2 minute tolerance
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Request timestamp stale. Server time: {now.isoformat()}, Request time: {request_time.isoformat()}",
        )

    # 4. Verify signature
    # Load public key
    public_key = load_public_key(credential.public_key)

    # Build canonical request for verification
    # Use FIXED canonical path (not client-selected) to prevent path confusion attacks
    # Clients MUST use this exact path when signing: "/api/authorize"
    CANONICAL_AUTH_PATH = "/api/authorize"

    body_dict = {
        "request_id": request.request_id,
        "idempotency_key": request.idempotency_key,
        "agent_id": request.agent_id,
        "key_id": request.key_id,
        "nonce": request.nonce,
        "timestamp": request.timestamp.isoformat(),
        "amount_cents": request.amount_cents,
        "currency": request.currency,
        "merchant_id": request.merchant_id,
        "merchant_category": request.merchant_category,
        "description": request.description,
    }
    body_hash = compute_body_hash(body_dict)

    canonical = canonical_request_string(
        method="POST",
        path=CANONICAL_AUTH_PATH,
        timestamp=request.timestamp.isoformat(),
        nonce=request.nonce,
        body_hash=body_hash,
    )

    if not verify_signature(public_key, canonical.encode(), request.signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    # 5. Verify agent identity matches credential (defense in depth)
    # The credential was fetched using agent.id and request.key_id, so this
    # implicitly verifies the agent_id matches. But we double-check:
    if credential.agent_id != agent.id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credential does not belong to requested agent",
        )

    # 6. Check idempotency key and payment intent fingerprint
    if request.idempotency_key:
        try:
            existing = check_idempotency(
                db,
                request.idempotency_key,
                agent_id=agent.id,
                amount_cents=request.amount_cents,
                currency=request.currency,
                merchant_id=request.merchant_id,
                merchant_category=request.merchant_category,
                description=request.description,
            )
        except ValueError as e:
            # Conflicting intent for same idempotency key
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e),
            )

        if existing:
            # Legitimate retry: consume a fresh nonce, return cached decision without re-evaluating policy
            if not consume_nonce(db, agent.id, request.nonce):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or already used nonce",
                )
            # Commit the nonce consumption so it cannot be reused
            db.commit()

            # Get current daily budget usage for accurate remaining calculation
            policy = get_active_policy(db, agent.id)
            if policy:
                usage = db.execute(
                    select(DailyBudgetUsage).where(
                        DailyBudgetUsage.agent_id == agent.id,
                        DailyBudgetUsage.usage_date == _get_usage_date(),
                    )
                ).scalar_one_or_none()
                daily_spent_now = (usage.reserved_cents + usage.captured_cents) if usage else 0
                daily_budget_remaining = max(0, policy.daily_budget_cents - daily_spent_now)
            else:
                daily_budget_remaining = 0

            return AuthorizationResponse(
                request_id=existing.request_id,
                decision=existing.decision.value,
                reasons=json.loads(existing.reasons),
                policy_violations=json.loads(existing.policy_violations) if existing.policy_violations else None,
                daily_spent_before_cents=existing.daily_spent_before_cents,
                daily_spent_after_cents=existing.daily_spent_after_cents,
                daily_budget_remaining_cents=daily_budget_remaining,
                decided_at=existing.decided_at,
                risk_score=existing.risk_score,
                risk_level=existing.risk_level,
                anomaly_signals=json.loads(existing.anomaly_signals) if existing.anomaly_signals else [],
                anomaly_explanation=existing.anomaly_explanation,
                detection_method=existing.detection_method,
            )

    # 7. Consume nonce (replay protection) - for new requests
    if not consume_nonce(db, agent.id, request.nonce):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or already used nonce",
        )

    # 8. Get active spending policy
    policy = get_active_policy(db, agent.id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active spending policy for this agent",
        )

    # 9. Evaluate authorization (policy checks)
    auth_service = AuthorizationService(db)
    decision, reasons, violations, daily_before, daily_after = auth_service.evaluate(
        agent=agent,
        credential=credential,
        policy=policy,
        amount_cents=request.amount_cents,
        currency=request.currency,
        merchant_id=request.merchant_id,
        merchant_category=request.merchant_category,
        description=request.description,
        idempotency_key=request.idempotency_key,
    )

    # 10. Anomaly Detection (Phase 4) - runs after policy checks pass
    risk_score = 0
    risk_level = "minimal"
    anomaly_signals = []
    anomaly_explanation = None
    detection_method = "rule_based"

    if decision == AuthorizationDecision.ALLOW:
        # Only run anomaly detection for requests that pass policy checks
        anomaly_service = AnomalyDetectionService(db)
        assessment = anomaly_service.assess_transaction(
            agent_id=agent.id,
            amount_cents=request.amount_cents,
            merchant_id=request.merchant_id,
            currency=request.currency,
        )

        risk_score = normalize_risk_score(assessment["risk_score"])
        risk_level = assessment["risk_severity"]
        anomaly_signals = assessment["anomaly_signals"]
        detection_method = assessment["detection_method"]

        # Generate human-readable explanation
        if anomaly_signals:
            signal_descriptions = [s["description"] for s in anomaly_signals]
            anomaly_explanation = "; ".join(signal_descriptions)
        else:
            anomaly_explanation = "No anomalies detected. Transaction aligns with historical patterns."

        # Integrate risk into decision (hard policy violations cannot be overridden)
        if anomaly_service.should_block(risk_score):
            # Critical risk - BLOCK even though policy passed
            decision = AuthorizationDecision.BLOCK
            reasons.append(f"Anomaly detection: Risk score {risk_score} exceeds block threshold")
        elif anomaly_service.should_trigger_review(risk_score):
            # High risk - REVIEW (requires human intervention)
            decision = AuthorizationDecision.REVIEW
            reasons.append(f"Anomaly detection: Risk score {risk_score} triggers review")

        # AuthorizationService places a provisional daily-budget hold before
        # anomaly detection. Risk escalations must release that hold; REVIEW
        # and BLOCK are never budget-authorized.
        if decision != AuthorizationDecision.ALLOW:
            from app.services.auth import release_budget
            if daily_after > daily_before:
                release_budget(db, agent.id, request.amount_cents)
                daily_after -= request.amount_cents

    # 11. Record decision for audit trail and commit atomically
    # Handle race condition: if another request with same idempotency_key committed
    # between our check and this flush/commit, we'll get a UNIQUE constraint violation.
    try:
        record_authorization_decision(
            db=db,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            agent=agent,
            credential=credential,
            policy=policy,
            amount_cents=request.amount_cents,
            currency=request.currency,
            merchant_id=request.merchant_id,
            merchant_category=request.merchant_category,
            description=request.description,
            decision=decision,
            reasons=reasons,
            violations=violations,
            daily_spent_before=daily_before,
            daily_spent_after=daily_after,
            risk_score=risk_score,
            risk_level=risk_level,
            anomaly_signals=anomaly_signals,
            anomaly_explanation=anomaly_explanation,
            detection_method=detection_method,
        )

        # 11. Commit the entire transaction atomically
        # This ensures nonce consumption, budget reservation, and decision recording
        # all succeed or fail together.
        db.commit()
    except IntegrityError as e:
        # Another request with the same idempotency_key beat us to the commit.
        # Rollback our transaction (releases budget reservation, nonce consumption, etc.)
        db.rollback()

        # Re-check idempotency to see what the other request decided
        if request.idempotency_key:
            try:
                existing = check_idempotency(
                    db,
                    request.idempotency_key,
                    agent_id=agent.id,
                    amount_cents=request.amount_cents,
                    currency=request.currency,
                    merchant_id=request.merchant_id,
                    merchant_category=request.merchant_category,
                    description=request.description,
                )
            except ValueError as ve:
                # Conflicting intent for same idempotency key - return 409 Conflict
                # The nonce was already consumed in the rolled-back transaction, so we don't need to consume it again
                # But we should NOT commit the rollback - it's already rolled back
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(ve),
                )

            if existing:
                # Another request with SAME intent succeeded - consume our nonce and return cached decision
                if not consume_nonce(db, agent.id, request.nonce):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid or already used nonce",
                    )
                db.commit()

                # Get current daily budget usage for accurate remaining calculation
                if policy:
                    usage = db.execute(
                        select(DailyBudgetUsage).where(
                            DailyBudgetUsage.agent_id == agent.id,
                            DailyBudgetUsage.usage_date == _get_usage_date(),
                        )
                    ).scalar_one_or_none()
                    daily_spent_now = (usage.reserved_cents + usage.captured_cents) if usage else 0
                    daily_budget_remaining = max(0, policy.daily_budget_cents - daily_spent_now)
                else:
                    daily_budget_remaining = 0

                return AuthorizationResponse(
                    request_id=existing.request_id,
                    decision=existing.decision.value,
                    reasons=json.loads(existing.reasons),
                    policy_violations=json.loads(existing.policy_violations) if existing.policy_violations else None,
                    daily_spent_before_cents=existing.daily_spent_before_cents,
                    daily_spent_after_cents=existing.daily_spent_after_cents,
                    daily_budget_remaining_cents=daily_budget_remaining,
                    decided_at=existing.decided_at,
                    risk_score=existing.risk_score,
                    risk_level=existing.risk_level,
                    anomaly_signals=json.loads(existing.anomaly_signals) if existing.anomaly_signals else [],
                    anomaly_explanation=existing.anomaly_explanation,
                    detection_method=existing.detection_method,
                )
            else:
                # This shouldn't happen - the UNIQUE constraint failed but no record exists?
                # Could be a different UNIQUE constraint (e.g., request_id).
                # Return a retryable error.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Concurrent request conflict. Please retry with a fresh nonce.",
                )
        else:
            # No idempotency key - this is a different UNIQUE constraint violation
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Concurrent request conflict. Please retry.",
            )

    # 12. Return response
    daily_budget_remaining = max(0, policy.daily_budget_cents - daily_after)

    return AuthorizationResponse(
        request_id=request.request_id,
        decision=decision.value,
        reasons=reasons,
        policy_violations=violations if violations else None,
        daily_spent_before_cents=daily_before,
        daily_spent_after_cents=daily_after,
        daily_budget_remaining_cents=daily_budget_remaining,
        decided_at=datetime.utcnow(),
        risk_score=risk_score,
        risk_level=risk_level,
        anomaly_signals=anomaly_signals,
        anomaly_explanation=anomaly_explanation,
        detection_method=detection_method,
    )


# =============================================================================
# Authorization Decision History
# =============================================================================


@router.get(
    "/decisions",
    response_model=AuthorizationDecisionListResponse,
    dependencies=[Depends(verify_admin_api_key)],
    summary="Get authorization decision history",
)
async def get_authorization_decisions(
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    decision: Optional[str] = Query(None, description="Filter by decision (allow, block, review)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> AuthorizationDecisionListResponse:
    """
    Get paginated history of authorization decisions.

    Can filter by agent_id and decision outcome.
    """
    from sqlalchemy import select, func

    from app.models import AuthorizationDecisionRecord

    query = select(AuthorizationDecisionRecord)
    count_query = select(func.count(AuthorizationDecisionRecord.id))

    if agent_id:
        agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent '{agent_id}' not found",
            )
        query = query.where(AuthorizationDecisionRecord.agent_id == agent.id)
        count_query = count_query.where(AuthorizationDecisionRecord.agent_id == agent.id)

    if decision:
        try:
            decision_enum = AuthorizationDecision(decision.lower())
            query = query.where(AuthorizationDecisionRecord.decision == decision_enum)
            count_query = count_query.where(AuthorizationDecisionRecord.decision == decision_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid decision value: {decision}. Must be one of: allow, block, review",
            )

    total = db.execute(count_query).scalar_one()

    query = query.order_by(AuthorizationDecisionRecord.decided_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    records = db.execute(query).scalars().all()

    items = []
    for record in records:
        items.append(AuthorizationDecisionResponse(
            id=record.id,
            request_id=record.request_id,
            idempotency_key=record.idempotency_key,
            agent_id=record.agent_id,
            credential_id=record.credential_id,
            policy_id=record.policy_id,
            amount_cents=record.amount_cents,
            currency=record.currency,
            merchant_id=record.merchant_id,
            merchant_category=record.merchant_category,
            description=record.description,
            decision=record.decision.value,
            reasons=json.loads(record.reasons),
            policy_violations=json.loads(record.policy_violations) if record.policy_violations else None,
            daily_spent_before_cents=record.daily_spent_before_cents,
            daily_spent_after_cents=record.daily_spent_after_cents,
            decided_at=record.decided_at,
            risk_score=record.risk_score,
            risk_level=record.risk_level,
            anomaly_signals=record.anomaly_signals,
            anomaly_explanation=record.anomaly_explanation,
            detection_method=record.detection_method,
        ))

    return AuthorizationDecisionListResponse.create(items, total, page, page_size)


@router.get(
    "/decisions/{request_id}",
    response_model=AuthorizationDecisionResponse,
    dependencies=[Depends(verify_admin_api_key)],
    summary="Get specific authorization decision by request ID",
)
async def get_authorization_decision(
    request_id: str,
    db: Session = Depends(get_db),
) -> AuthorizationDecisionResponse:
    """Get a specific authorization decision by request ID."""
    from app.models import AuthorizationDecisionRecord

    record = db.execute(
        select(AuthorizationDecisionRecord).where(
            AuthorizationDecisionRecord.request_id == request_id
        )
    ).scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Authorization decision '{request_id}' not found",
        )

    return AuthorizationDecisionResponse(
        id=record.id,
        request_id=record.request_id,
        idempotency_key=record.idempotency_key,
        agent_id=record.agent_id,
        credential_id=record.credential_id,
        policy_id=record.policy_id,
        amount_cents=record.amount_cents,
        currency=record.currency,
        merchant_id=record.merchant_id,
        merchant_category=record.merchant_category,
        description=record.description,
        decision=record.decision.value,
        reasons=json.loads(record.reasons),
        policy_violations=json.loads(record.policy_violations) if record.policy_violations else None,
        daily_spent_before_cents=record.daily_spent_before_cents,
        daily_spent_after_cents=record.daily_spent_after_cents,
        decided_at=record.decided_at,
        risk_score=record.risk_score,
        risk_level=record.risk_level,
        anomaly_signals=record.anomaly_signals,
        anomaly_explanation=record.anomaly_explanation,
        detection_method=record.detection_method,
    )


# =============================================================================
# Authorization Reservation Lifecycle (Admin Only)
# =============================================================================


@router.post(
    "/reservations/capture",
    response_model=ReservationLifecycleResponse,
    summary="Capture an authorization reservation (admin only)",
    dependencies=[Depends(verify_admin_api_key)],
)
async def capture_authorization_reservation(
    request: ReservationCaptureRequest,
    db: Session = Depends(get_db),
) -> ReservationLifecycleResponse:
    """
    Capture a reservation (move from RESERVED to CAPTURED).

    This is an administrative operation for completing a payment.
    Transfers budget from reserved_cents to captured_cents atomically.

    Idempotent: calling on an already CAPTURED reservation returns success
    with the current reservation state (no double capture).
    """
    # Verify reservation exists and is in RESERVED state
    reservation = get_reservation_by_auth_decision(db, request.auth_decision_id)
    if not reservation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation for auth decision {request.auth_decision_id} not found",
        )

    if reservation.agent_id != request.agent_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent ID does not match reservation",
        )

    if reservation.amount_cents != request.amount_cents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount does not match reservation",
        )

    success = capture_reservation(
        db=db,
        auth_decision_id=request.auth_decision_id,
        agent_id=request.agent_id,
        amount_cents=request.amount_cents,
    )

    if not success:
        # Check current state to provide informative response
        reservation = get_reservation_by_auth_decision(db, request.auth_decision_id)
        if reservation:
            if reservation.status == ReservationStatus.CAPTURED:
                return ReservationLifecycleResponse(
                    success=True,
                    message="Reservation already captured",
                    reservation=AuthorizationReservationResponse.model_validate(reservation),
                )
            elif reservation.status in (ReservationStatus.RELEASED, ReservationStatus.EXPIRED):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Cannot capture reservation in {reservation.status.value} state",
                )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reservation not in capturable state or insufficient budget",
        )

    db.commit()
    reservation = get_reservation_by_auth_decision(db, request.auth_decision_id)

    return ReservationLifecycleResponse(
        success=True,
        message="Reservation captured successfully",
        reservation=AuthorizationReservationResponse.model_validate(reservation) if reservation else None,
    )


@router.post(
    "/reservations/release",
    response_model=ReservationLifecycleResponse,
    summary="Release an authorization reservation (admin only)",
    dependencies=[Depends(verify_admin_api_key)],
)
async def release_authorization_reservation(
    request: ReservationReleaseRequest,
    db: Session = Depends(get_db),
) -> ReservationLifecycleResponse:
    """
    Release a reservation (move from RESERVED to RELEASED).

    This is an administrative operation for cancelling an authorization.
    Returns budget from reserved_cents to available.

    Idempotent: calling on an already RELEASED reservation returns success
    with the current reservation state (no double release).
    """
    # Verify reservation exists and is in RESERVED state
    reservation = get_reservation_by_auth_decision(db, request.auth_decision_id)
    if not reservation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation for auth decision {request.auth_decision_id} not found",
        )

    if reservation.agent_id != request.agent_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent ID does not match reservation",
        )

    if reservation.amount_cents != request.amount_cents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount does not match reservation",
        )

    success = release_reservation(
        db=db,
        auth_decision_id=request.auth_decision_id,
        agent_id=request.agent_id,
        amount_cents=request.amount_cents,
    )

    if not success:
        # Check current state to provide informative response
        reservation = get_reservation_by_auth_decision(db, request.auth_decision_id)
        if reservation:
            if reservation.status == ReservationStatus.RELEASED:
                return ReservationLifecycleResponse(
                    success=True,
                    message="Reservation already released",
                    reservation=AuthorizationReservationResponse.model_validate(reservation),
                )
            elif reservation.status == ReservationStatus.CAPTURED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot release a captured reservation",
                )
            elif reservation.status == ReservationStatus.EXPIRED:
                return ReservationLifecycleResponse(
                    success=True,
                    message="Reservation already expired",
                    reservation=AuthorizationReservationResponse.model_validate(reservation),
                )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reservation not in releasable state",
        )

    db.commit()
    reservation = get_reservation_by_auth_decision(db, request.auth_decision_id)

    return ReservationLifecycleResponse(
        success=True,
        message="Reservation released successfully",
        reservation=AuthorizationReservationResponse.model_validate(reservation) if reservation else None,
    )


@router.post(
    "/reservations/expire",
    response_model=ReservationLifecycleResponse,
    summary="Expire old reservations (admin only)",
    dependencies=[Depends(verify_admin_api_key)],
)
async def expire_old_authorization_reservations(
    request: ReservationExpireRequest,
    db: Session = Depends(get_db),
) -> ReservationLifecycleResponse:
    """
    Expire reservations older than max_age_hours that are still in RESERVED state.

    This is an administrative operation for cleaning up stale reservations.
    Returns budget from reserved_cents to available for each expired reservation.

    Returns count of expired reservations.

    Only processes reservations transitioned during this invocation to avoid
    double-releasing budget on repeated calls.
    """
    expired_count = expire_old_reservations(db, max_age_hours=request.max_age_hours)
    db.commit()

    return ReservationLifecycleResponse(
        success=True,
        message=f"Expired {expired_count} reservations",
    )


@router.get(
    "/reservations",
    response_model=AuthorizationReservationListResponse,
    dependencies=[Depends(verify_admin_api_key)],
    summary="List authorization reservations",
)
async def list_authorization_reservations(
    agent_id: Optional[int] = Query(None, description="Filter by agent ID"),
    status: Optional[str] = Query(None, description="Filter by status (reserved, captured, released, expired)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> AuthorizationReservationListResponse:
    """Get paginated list of authorization reservations."""
    from sqlalchemy import func

    query = select(AuthorizationReservation)
    count_query = select(func.count(AuthorizationReservation.id))

    if agent_id is not None:
        query = query.where(AuthorizationReservation.agent_id == agent_id)
        count_query = count_query.where(AuthorizationReservation.agent_id == agent_id)

    if status is not None:
        try:
            status_enum = ReservationStatus(status.lower())
            query = query.where(AuthorizationReservation.status == status_enum)
            count_query = count_query.where(AuthorizationReservation.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status}. Must be one of: reserved, captured, released, expired",
            )

    total = db.execute(count_query).scalar_one()

    query = query.order_by(AuthorizationReservation.reserved_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    records = db.execute(query).scalars().all()

    items = [AuthorizationReservationResponse.model_validate(r) for r in records]

    return AuthorizationReservationListResponse.create(items, total, page, page_size)


@router.get(
    "/reservations/{auth_decision_id}",
    response_model=AuthorizationReservationResponse,
    dependencies=[Depends(verify_admin_api_key)],
    summary="Get reservation by authorization decision ID",
)
async def get_authorization_reservation(
    auth_decision_id: int,
    db: Session = Depends(get_db),
) -> AuthorizationReservationResponse:
    """Get a specific authorization reservation by auth decision ID."""
    reservation = get_reservation_by_auth_decision(db, auth_decision_id)

    if not reservation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation for auth decision {auth_decision_id} not found",
        )

    return AuthorizationReservationResponse.model_validate(reservation)
