"""Spending policy management API endpoints."""

import json
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_admin, verify_admin_api_key
from app.core.database import get_db
from app.models import Agent, SpendingPolicy, PolicyStatus
from app.schemas import (
    SpendingPolicyCreateRequest,
    SpendingPolicyUpdateRequest,
    SpendingPolicyRevokeRequest,
    SpendingPolicyResponse,
)
from app.services import (
    create_spending_policy,
    get_active_policy,
    revoke_policy,
    parse_policy_currencies,
    parse_policy_allowed_merchants,
    parse_policy_blocked_merchants,
)

router = APIRouter(prefix="/policies", tags=["policies"])


# =============================================================================
# Policy CRUD
# =============================================================================


@router.post(
    "",
    response_model=SpendingPolicyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a spending policy for an agent (admin only)",
    dependencies=[Depends(verify_admin_api_key)],
)
async def create_policy(
    agent_id: str = Query(..., description="Agent identifier"),
    request: SpendingPolicyCreateRequest = ...,
    db: Session = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
) -> SpendingPolicyResponse:
    """
    Create a delegated spending authorization policy for an agent.

    Only admin can create policies. The policy's owner_id is bound to the
    agent's registered owner (owner_type + owner_email), not the request body.

    The policy defines:
    - Per-transaction spending limit (in cents)
    - Daily budget (in cents)
    - Allowed currencies (ISO 4217 codes)
    - Optional allowed/blocked merchant lists
    - Expiration date

    The policy is enforced on every authorization request.

    **Requires admin authentication** via X-Admin-API-Key header.
    """
    agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )

    # Check if policy already exists
    existing = db.query(SpendingPolicy).filter(
        SpendingPolicy.agent_id == agent.id,
        SpendingPolicy.status == PolicyStatus.ACTIVE,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent '{agent_id}' already has an active spending policy. Revoke it first.",
        )

    # Validate currencies
    if not request.allowed_currencies:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one allowed currency is required",
        )

    # Validate limits
    if request.per_transaction_limit_cents > request.daily_budget_cents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Per-transaction limit cannot exceed daily budget",
        )

    # Bind owner_id to agent's actual registered owner, NOT request body
    # Format: "{owner_type}:{owner_email}"
    owner_id = f"{agent.owner_type}:{agent.owner_email}"

    policy = create_spending_policy(
        db=db,
        agent=agent,
        owner_id=owner_id,
        per_transaction_limit_cents=request.per_transaction_limit_cents,
        daily_budget_cents=request.daily_budget_cents,
        allowed_currencies=request.allowed_currencies,
        allowed_merchant_ids=request.allowed_merchant_ids,
        blocked_merchant_ids=request.blocked_merchant_ids,
        expires_in_days=request.expires_in_days,
    )

    return SpendingPolicyResponse(
        id=policy.id,
        agent_id=policy.agent_id,
        owner_id=policy.owner_id,
        per_transaction_limit_cents=policy.per_transaction_limit_cents,
        daily_budget_cents=policy.daily_budget_cents,
        allowed_currencies=parse_policy_currencies(policy),
        allowed_merchant_ids=parse_policy_allowed_merchants(policy),
        blocked_merchant_ids=parse_policy_blocked_merchants(policy),
        status=policy.status.value,
        effective_at=policy.effective_at,
        expires_at=policy.expires_at,
        revoked_at=policy.revoked_at,
        revoked_by=policy.revoked_by,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


@router.get(
    "/{agent_id}",
    response_model=SpendingPolicyResponse,
    summary="Get active spending policy for an agent",
)
async def get_policy(
    agent_id: str,
    db: Session = Depends(get_db),
) -> SpendingPolicyResponse:
    """Get the active spending policy for an agent."""
    agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )

    policy = get_active_policy(db, agent.id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active spending policy found for this agent",
        )

    return SpendingPolicyResponse(
        id=policy.id,
        agent_id=policy.agent_id,
        owner_id=policy.owner_id,
        per_transaction_limit_cents=policy.per_transaction_limit_cents,
        daily_budget_cents=policy.daily_budget_cents,
        allowed_currencies=parse_policy_currencies(policy),
        allowed_merchant_ids=parse_policy_allowed_merchants(policy),
        blocked_merchant_ids=parse_policy_blocked_merchants(policy),
        status=policy.status.value,
        effective_at=policy.effective_at,
        expires_at=policy.expires_at,
        revoked_at=policy.revoked_at,
        revoked_by=policy.revoked_by,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


@router.patch(
    "/{agent_id}",
    response_model=SpendingPolicyResponse,
    summary="Update a spending policy (limited fields, admin only)",
    dependencies=[Depends(verify_admin_api_key)],
)
async def update_policy(
    agent_id: str,
    request: SpendingPolicyUpdateRequest,
    db: Session = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
) -> SpendingPolicyResponse:
    """
    Update a spending policy.

    Only non-financial fields can be updated (merchant lists, expiration).
    Financial limits (per-transaction, daily budget) cannot be changed
    after creation - create a new policy instead.

    **Requires admin authentication** via X-Admin-API-Key header.
    """
    agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )

    policy = get_active_policy(db, agent.id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active spending policy found for this agent",
        )

    # Only admin can update policies

    # Update allowed fields
    if request.allowed_merchant_ids is not None:
        policy.allowed_merchant_ids = json.dumps(request.allowed_merchant_ids)
    if request.blocked_merchant_ids is not None:
        policy.blocked_merchant_ids = json.dumps(request.blocked_merchant_ids)
    if request.expires_in_days is not None:
        policy.expires_at = datetime.utcnow() + timedelta(days=request.expires_in_days)

    policy.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(policy)

    return SpendingPolicyResponse(
        id=policy.id,
        agent_id=policy.agent_id,
        owner_id=policy.owner_id,
        per_transaction_limit_cents=policy.per_transaction_limit_cents,
        daily_budget_cents=policy.daily_budget_cents,
        allowed_currencies=parse_policy_currencies(policy),
        allowed_merchant_ids=parse_policy_allowed_merchants(policy),
        blocked_merchant_ids=parse_policy_blocked_merchants(policy),
        status=policy.status.value,
        effective_at=policy.effective_at,
        expires_at=policy.expires_at,
        revoked_at=policy.revoked_at,
        revoked_by=policy.revoked_by,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


@router.post(
    "/{agent_id}/revoke",
    response_model=SpendingPolicyResponse,
    summary="Revoke a spending policy (admin only)",
    dependencies=[Depends(verify_admin_api_key)],
)
async def revoke_agent_policy(
    agent_id: str,
    request: SpendingPolicyRevokeRequest,
    db: Session = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
) -> SpendingPolicyResponse:
    """
    Revoke an agent's spending policy.

    Revoked policies cannot be used for authorization.

    **Requires admin authentication** via X-Admin-API-Key header.
    """
    agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )

    policy = get_active_policy(db, agent.id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active spending policy found for this agent",
        )

    # Only admin can revoke policies
    revoked_policy = revoke_policy(
        db=db,
        policy=policy,
        revoked_by=admin_id,
    )

    return SpendingPolicyResponse(
        id=revoked_policy.id,
        agent_id=revoked_policy.agent_id,
        owner_id=revoked_policy.owner_id,
        per_transaction_limit_cents=revoked_policy.per_transaction_limit_cents,
        daily_budget_cents=revoked_policy.daily_budget_cents,
        allowed_currencies=parse_policy_currencies(revoked_policy),
        allowed_merchant_ids=parse_policy_allowed_merchants(revoked_policy),
        blocked_merchant_ids=parse_policy_blocked_merchants(revoked_policy),
        status=revoked_policy.status.value,
        effective_at=revoked_policy.effective_at,
        expires_at=revoked_policy.expires_at,
        revoked_at=revoked_policy.revoked_at,
        revoked_by=revoked_policy.revoked_by,
        created_at=revoked_policy.created_at,
        updated_at=revoked_policy.updated_at,
    )