"""Authentication and credential management API endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_admin, verify_admin_api_key
from app.core.database import get_db
from app.models import Agent, AgentCredential, CredentialStatus
from app.schemas import (
    AgentRegistrationRequest,
    AgentRegistrationResponse,
    CredentialResponse,
    CredentialRevokeRequest,
    CredentialStatusResponse,
    NonceResponse,
)
from app.services import (
    register_agent_credential,
    get_active_credential,
    revoke_credential,
    check_credential_valid,
    create_nonce,
    consume_nonce,
    cleanup_expired_nonces,
    load_public_key,
    verify_signature,
    canonical_request_string,
    compute_body_hash,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


# =============================================================================
# Agent Registration with Credential
# =============================================================================


@router.post(
    "/register",
    response_model=AgentRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new agent with cryptographic credential (admin only)",
    dependencies=[Depends(verify_admin_api_key)],
)
async def register_agent(
    request: AgentRegistrationRequest,
    db: Session = Depends(get_db),
) -> AgentRegistrationResponse:
    """
    Register a new agent with an Ed25519 public key.

    The agent can then use the corresponding private key to sign API requests.
    The public key is stored (never the private key) and used for signature verification.

    - **agent_id**: Unique identifier for the agent (e.g., "AGT-2026-001")
    - **public_key_pem**: PEM-encoded Ed25519 public key
    - **expires_in_days**: Optional credential validity period (default: no expiration)

    Returns the agent ID, key ID, and credential details.

    **Requires admin authentication** via X-Admin-API-Key header.
    """
    # Check if agent_id already exists
    existing = db.query(Agent).filter(Agent.agent_id == request.agent_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent with ID '{request.agent_id}' already exists",
        )

    # Validate public key format
    try:
        public_key = load_public_key(request.public_key_pem)
        if not hasattr(public_key, "verify"):
            raise ValueError("Not a valid public key")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid public key format: {str(e)}",
        )

    # Create agent
    agent = Agent(
        agent_id=request.agent_id,
        name=request.name,
        description=request.description,
        owner_type=request.owner_type,
        owner_name=request.owner_name,
        owner_email=request.owner_email,
        owner_contact=request.owner_contact,
        daily_limit_usd=0,  # Will be set by spending policy
        monthly_limit_usd=0,
        status="pending_review",
    )
    db.add(agent)
    db.flush()  # Get agent ID

    # Register credential
    credential = register_agent_credential(
        db=db,
        agent=agent,
        public_key_pem=request.public_key_pem,
        expires_in_days=request.expires_in_days,
    )

    return AgentRegistrationResponse(
        agent_id=agent.agent_id,
        key_id=credential.key_id,
        credential_id=credential.id,
        issued_at=credential.issued_at,
        expires_at=credential.expires_at,
        message="Agent registered successfully. Use the key_id for signing requests.",
    )


# =============================================================================
# Credential Status & Management
# =============================================================================


@router.get(
    "/credentials/{agent_id}",
    response_model=CredentialResponse,
    summary="Get agent credential details",
)
async def get_credential(
    agent_id: str,
    key_id: Optional[str] = Query(None, description="Specific key ID to retrieve"),
    db: Session = Depends(get_db),
) -> CredentialResponse:
    """
    Get credential details for an agent.

    If key_id is not provided, returns the active credential for the agent.
    """
    agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )

    if key_id:
        credential = db.query(AgentCredential).filter(
            AgentCredential.agent_id == agent.id,
            AgentCredential.key_id == key_id,
        ).first()
    else:
        credential = db.query(AgentCredential).filter(
            AgentCredential.agent_id == agent.id,
            AgentCredential.status == CredentialStatus.ACTIVE,
        ).first()

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found",
        )

    return CredentialResponse.model_validate(credential)


@router.get(
    "/credentials/{agent_id}/status",
    response_model=CredentialStatusResponse,
    summary="Check credential validity status",
)
async def check_credential_status(
    agent_id: str,
    key_id: str = Query(..., description="Credential key ID to check"),
    db: Session = Depends(get_db),
) -> CredentialStatusResponse:
    """
    Check if a credential is valid (active, not expired, not revoked).

    Used by agents to verify their credential status before making requests.
    """
    agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )

    credential = get_active_credential(db, agent.id, key_id)
    if not credential:
        return CredentialStatusResponse(
            key_id=key_id,
            status="not_found",
            is_valid=False,
            message="Credential not found or not active",
        )

    is_valid, message = check_credential_valid(credential)

    return CredentialStatusResponse(
        key_id=credential.key_id,
        status=credential.status.value,
        is_valid=is_valid,
        expires_at=credential.expires_at,
        message=message,
    )


@router.post(
    "/credentials/{agent_id}/revoke",
    response_model=CredentialResponse,
    summary="Revoke an agent credential (admin only)",
    dependencies=[Depends(verify_admin_api_key)],
)
async def revoke_agent_credential(
    agent_id: str,
    key_id: str = Query(..., description="Key ID of credential to revoke"),
    request: CredentialRevokeRequest = ...,
    db: Session = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
) -> CredentialResponse:
    """
    Revoke an agent's cryptographic credential.

    Requires admin authentication. Revoked credentials cannot be used for signing.
    """
    agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )

    credential = db.query(AgentCredential).filter(
        AgentCredential.agent_id == agent.id,
        AgentCredential.key_id == key_id,
    ).first()

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found",
        )

    if credential.status == CredentialStatus.REVOKED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Credential already revoked",
        )

    revoked_credential = revoke_credential(
        db=db,
        credential=credential,
        revoked_by=admin_id,
        reason=request.reason,
    )

    return CredentialResponse.model_validate(revoked_credential)


# =============================================================================
# Nonce Challenge (for replay protection)
# =============================================================================


@router.post(
    "/challenge",
    response_model=NonceResponse,
    summary="Get a nonce for signing a request",
)
async def get_nonce(
    agent_id: str = Query(..., description="Agent identifier"),
    key_id: str = Query(..., description="Credential key identifier"),
    db: Session = Depends(get_db),
) -> NonceResponse:
    """
    Get a single-use nonce for signing an authorization request.

    The nonce must be included in the signed request and will be consumed
    upon verification to prevent replay attacks.

    - Expires in 5 minutes (300 seconds)
    - Can only be used once
    - Bound to the specific agent and key_id
    """
    agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )

    credential = get_active_credential(db, agent.id, key_id)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active credential not found for this agent and key_id",
        )

    is_valid, message = check_credential_valid(credential)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Credential invalid: {message}",
        )

    nonce, expires_at = create_nonce(db, agent.id)

    return NonceResponse(
        nonce=nonce,
        expires_at=expires_at,
        message="Use this nonce in your signed authorization request. It expires in 5 minutes and can only be used once.",
    )


# =============================================================================
# Admin: Cleanup expired nonces
# =============================================================================


@router.post(
    "/admin/cleanup-nonces",
    summary="Clean up expired nonces (admin only)",
    dependencies=[Depends(verify_admin_api_key)],
)
async def cleanup_nonces(
    db: Session = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
) -> dict:
    """Remove expired nonces from the store. Admin only."""
    deleted = cleanup_expired_nonces(db)
    return {"deleted": deleted, "message": f"Cleaned up {deleted} expired nonces by {admin_id}"}