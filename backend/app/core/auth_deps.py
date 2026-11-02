"""Authentication dependencies for FastAPI routes."""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models import Agent, AgentCredential, AuthorizationDecisionRecord, CredentialStatus
from app.services import (
    load_public_key,
    verify_signature,
    canonical_request_string,
    compute_body_hash,
    consume_nonce,
    get_active_credential,
    check_credential_valid,
)

# Timestamp tolerance (2 minutes)
TIMESTAMP_TOLERANCE_SECONDS = 120


def _constant_time_compare(val1: str, val2: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    return hmac.compare_digest(val1, val2)


def _get_admin_key_or_fail() -> str:
    """Get admin API key from settings, fail closed if not configured."""
    settings = get_settings()
    admin_key = settings.admin_api_key
    if not admin_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API key not configured. Set ADMIN_API_KEY environment variable.",
        )
    return admin_key


def verify_admin_api_key(
    x_admin_api_key: str = Header(..., alias="X-Admin-API-Key"),
) -> None:
    """Verify admin API key from header using constant-time comparison."""
    expected_key = _get_admin_key_or_fail()
    if not _constant_time_compare(x_admin_api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin API key",
        )


def get_current_admin(
    db: Session = Depends(get_db),
    x_admin_api_key: str = Header(..., alias="X-Admin-API-Key"),
) -> str:
    """Get admin identity after verifying API key."""
    expected_key = _get_admin_key_or_fail()
    if not _constant_time_compare(x_admin_api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin API key",
        )
    return "admin"


# X-Owner-ID is NOT used for authentication. It is only used for audit logging.
# All privileged operations require X-Admin-API-Key.
def get_requester_identity(
    x_admin_api_key: str = Header(None, alias="X-Admin-API-Key"),
) -> str:
    """Get requester identity - only admin is accepted for privileged operations."""
    if x_admin_api_key:
        expected_key = _get_admin_key_or_fail()
        if _constant_time_compare(x_admin_api_key, expected_key):
            return "admin"
    # For privileged endpoints, this will fail due to verify_admin_api_key dependency
    return "unauthenticated"


# =============================================================================
# Shared Agent Authentication Logic for Checkout Status
# =============================================================================


def _verify_agent_checkout_auth(
    request: Request,
    authorization_decision_id: int,
    db: Session,
    require_admin_or_agent: bool = True,
) -> Tuple[Optional[str], Optional[Agent], Optional[AgentCredential]]:
    """
    Shared logic to verify agent/admin authentication for checkout status.

    Args:
        request: The incoming request
        authorization_decision_id: The authorization decision ID to access
        db: Database session
        require_admin_or_agent: If True, raises HTTPException on auth failure.
                                If False, returns (None, None, None) on failure.

    Returns:
        Tuple of (requester_type, agent, credential) where requester_type is:
        - "admin" for admin access (agent and credential are None)
        - "agent" for agent access
        - None if unauthenticated (only when require_admin_or_agent=False)

    Raises:
        HTTPException: On authentication/authorization failure (when require_admin_or_agent=True)
    """
    # Check for admin API key first
    admin_key_header = request.headers.get("X-Admin-API-Key")
    if admin_key_header:
        expected_key = _get_admin_key_or_fail()
        if _constant_time_compare(admin_key_header, expected_key):
            # Admin authenticated - can access any authorization decision
            return "admin", None, None
        else:
            if require_admin_or_agent:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid admin API key",
                )
            return None, None, None

    # Agent authentication - require signed request
    # Get required headers
    agent_id_header = request.headers.get("X-Agent-Id")
    key_id_header = request.headers.get("X-Key-Id")
    nonce_header = request.headers.get("X-Nonce")
    timestamp_header = request.headers.get("X-Timestamp")
    signature_header = request.headers.get("X-Signature")

    if not all([agent_id_header, key_id_header, nonce_header, timestamp_header, signature_header]):
        if require_admin_or_agent:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing required authentication headers. Provide either X-Admin-API-Key or agent authentication headers (X-Agent-Id, X-Key-Id, X-Nonce, X-Timestamp, X-Signature)",
            )
        return None, None, None

    # Verify agent exists
    agent = db.query(Agent).filter(Agent.agent_id == agent_id_header).first()
    if not agent:
        if require_admin_or_agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent '{agent_id_header}' not found",
            )
        return None, None, None

    if agent.status.value != "active":
        if require_admin_or_agent:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Agent is {agent.status.value}. Only active agents can access checkout status.",
            )
        return None, None, None

    # Verify credential
    credential = get_active_credential(db, agent.id, key_id_header)
    if not credential:
        if require_admin_or_agent:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or inactive credential",
            )
        return None, None, None

    is_valid, message = check_credential_valid(credential)
    if not is_valid:
        if require_admin_or_agent:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Credential invalid: {message}",
            )
        return None, None, None

    # Verify timestamp - use timezone-aware comparison
    try:
        request_time = datetime.fromisoformat(timestamp_header.replace("Z", "+00:00"))
        # Ensure request_time is timezone-aware
        if request_time.tzinfo is None:
            request_time = request_time.replace(tzinfo=timezone.utc)
    except ValueError:
        if require_admin_or_agent:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid timestamp format. Use ISO 8601.",
            )
        return None, None, None

    now = datetime.now(timezone.utc)
    if abs((now - request_time).total_seconds()) > TIMESTAMP_TOLERANCE_SECONDS:
        if require_admin_or_agent:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Request timestamp stale. Server time: {now.isoformat()}, Request time: {request_time.isoformat()}",
            )
        return None, None, None

    # Verify signature
    public_key = load_public_key(credential.public_key)

    # Build canonical request for verification
    body_dict = {
        "authorization_decision_id": authorization_decision_id,
    }
    body_hash = compute_body_hash(body_dict)

    canonical = canonical_request_string(
        method="GET",
        path=f"/api/checkout/{authorization_decision_id}",
        timestamp=request_time.isoformat(),
        nonce=nonce_header,
        body_hash=body_hash,
    )

    if not verify_signature(public_key, canonical.encode(), signature_header):
        if require_admin_or_agent:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature",
            )
        return None, None, None

    # Verify nonce (replay protection) - atomic consumption
    if not consume_nonce(db, agent.id, nonce_header):
        if require_admin_or_agent:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or already used nonce",
            )
        return None, None, None

    # Verify agent owns the authorization decision
    auth_decision = db.query(AuthorizationDecisionRecord).filter(
        AuthorizationDecisionRecord.id == authorization_decision_id
    ).first()

    if not auth_decision:
        if require_admin_or_agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Authorization decision {authorization_decision_id} not found",
            )
        return None, None, None

    if auth_decision.agent_id != agent.id:
        if require_admin_or_agent:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this authorization decision",
            )
        return None, None, None

    # Commit the nonce consumption for get_checkout_requester (read-only dependency)
    if not require_admin_or_agent:
        db.commit()

    return "agent", agent, credential


def get_checkout_requester(
    request: Request,
    authorization_decision_id: int,
    db: Session = Depends(get_db),
) -> Tuple[Optional[str], Optional[Agent], Optional[AgentCredential]]:
    """
    Get the requester identity for checkout status endpoint.

    Returns tuple of (requester_type, agent, credential) where requester_type is:
    - "admin" for admin access
    - "agent" for agent access
    - None if unauthenticated (will be rejected by endpoint)

    This dependency does NOT raise for missing auth - it returns the identity for the endpoint to handle.
    But it DOES raise for invalid admin key and invalid signature.
    """
    # Check for admin API key first
    admin_key_header = request.headers.get("X-Admin-API-Key")
    if admin_key_header:
        expected_key = _get_admin_key_or_fail()
        if _constant_time_compare(admin_key_header, expected_key):
            return "admin", None, None
        else:
            # Invalid admin key - raise 401
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid admin API key",
            )

    # Agent authentication
    agent_id_header = request.headers.get("X-Agent-Id")
    key_id_header = request.headers.get("X-Key-Id")
    nonce_header = request.headers.get("X-Nonce")
    timestamp_header = request.headers.get("X-Timestamp")
    signature_header = request.headers.get("X-Signature")

    if not all([agent_id_header, key_id_header, nonce_header, timestamp_header, signature_header]):
        return None, None, None

    # Verify agent exists
    agent = db.query(Agent).filter(Agent.agent_id == agent_id_header).first()
    if not agent or agent.status.value != "active":
        return None, None, None

    # Verify credential
    credential = get_active_credential(db, agent.id, key_id_header)
    if not credential:
        return None, None, None

    is_valid, _ = check_credential_valid(credential)
    if not is_valid:
        return None, None, None

    # Verify timestamp
    try:
        request_time = datetime.fromisoformat(timestamp_header.replace("Z", "+00:00"))
    except ValueError:
        return None, None, None

    now = datetime.now(timezone.utc)
    if abs((now - request_time).total_seconds()) > TIMESTAMP_TOLERANCE_SECONDS:
        return None, None, None

    # Verify signature
    public_key = load_public_key(credential.public_key)
    body_dict = {"authorization_decision_id": authorization_decision_id}
    body_hash = compute_body_hash(body_dict)
    canonical = canonical_request_string(
        method="GET",
        path=f"/api/checkout/{authorization_decision_id}",
        timestamp=request_time.isoformat(),
        nonce=nonce_header,
        body_hash=body_hash,
    )

    if not verify_signature(public_key, canonical.encode(), signature_header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    # Verify nonce (replay protection)
    if not consume_nonce(db, agent.id, nonce_header):
        return None, None, None

    # Commit the nonce consumption
    db.commit()

    # Return agent info - ownership check is done in the endpoint
    return "agent", agent, credential