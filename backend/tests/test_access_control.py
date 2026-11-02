"""Access control and authorization boundary regression tests."""

import json
import time
from datetime import datetime, timedelta
from typing import Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Agent, AgentCredential, AgentStatus, SpendingPolicy, PolicyStatus, DailyBudgetUsage, CredentialStatus
from app.services import (
    register_agent_credential,
    create_spending_policy,
    compute_body_hash,
    canonical_request_string,
    revoke_credential,
)


def _generate_keypair() -> Tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]:
    """Generate a test Ed25519 keypair."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    return private_key, private_key.public_key()


def _public_key_to_pem(public_key: ed25519.Ed25519PublicKey) -> str:
    """Convert public key to PEM string."""
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def _sign_request(private_key: ed25519.Ed25519PrivateKey, canonical: str) -> str:
    """Sign a canonical request string and return base64 signature."""
    import base64
    signature = private_key.sign(canonical.encode())
    return base64.b64encode(signature).decode()


def create_test_agent_with_policy(
    db: Session,
    agent_id: str,
    private_key: ed25519.Ed25519PrivateKey,
    status: AgentStatus = AgentStatus.ACTIVE,
) -> Tuple[Agent, ed25519.Ed25519PrivateKey, str]:
    """Create a test agent with credential and spending policy."""
    public_key_pem = _public_key_to_pem(private_key.public_key())

    agent = Agent(
        agent_id=agent_id,
        name=f"Test Agent {agent_id}",
        description="Test agent for access control tests",
        status=status,
        owner_type="human",
        owner_name="Test Owner",
        owner_email="test@example.com",
        owner_contact=None,
    )
    db.add(agent)
    db.flush()

    credential = register_agent_credential(
        db=db,
        agent=agent,
        public_key_pem=public_key_pem,
        expires_in_days=365,
    )

    create_spending_policy(
        db=db,
        agent=agent,
        owner_id=f"human:test@example.com",
        per_transaction_limit_cents=10000,
        daily_budget_cents=50000,
        allowed_currencies=["USD"],
        allowed_merchant_ids=None,
        blocked_merchant_ids=None,
        expires_in_days=365,
    )

    db.commit()
    return agent, private_key, credential.key_id


def make_auth_payload(
    agent_id: str,
    key_id: str,
    private_key: ed25519.Ed25519PrivateKey,
    amount_cents: int = 1000,
    currency: str = "USD",
    merchant_id: str = "MERCH-001",
    merchant_category: str = "retail",
    description: str = "Test transaction",
    nonce: str = None,
    request_id: str = None,
    idempotency_key: str = None,
    timestamp: datetime = None,
) -> Tuple[dict, str]:
    """Create a signed authorization request payload."""
    if nonce is None:
        nonce = f"nonce-{int(time.time() * 1000)}"

    if request_id is None:
        request_id = f"req-{int(time.time() * 1000)}"

    if idempotency_key is None:
        idempotency_key = f"idem-{int(time.time() * 1000)}"

    if timestamp is None:
        timestamp = datetime.utcnow()

    body_dict = {
        "request_id": request_id,
        "idempotency_key": idempotency_key,
        "agent_id": agent_id,
        "key_id": key_id,
        "nonce": nonce,
        "timestamp": timestamp.isoformat(),
        "amount_cents": amount_cents,
        "currency": currency,
        "merchant_id": merchant_id,
        "merchant_category": merchant_category,
        "description": description,
    }
    body_hash = compute_body_hash(body_dict)

    canonical = canonical_request_string(
        method="POST",
        path="/api/authorize",
        timestamp=timestamp.isoformat(),
        nonce=nonce,
        body_hash=body_hash,
    )

    signature = _sign_request(private_key, canonical)

    payload = {
        "request_id": request_id,
        "idempotency_key": idempotency_key,
        "agent_id": agent_id,
        "key_id": key_id,
        "nonce": nonce,
        "timestamp": timestamp.isoformat(),
        "signature": signature,
        "amount_cents": amount_cents,
        "currency": currency,
        "merchant_id": merchant_id,
        "merchant_category": merchant_category,
        "description": description,
    }

    return payload, canonical


class TestAccessControl:
    """Tests for access control boundaries and authorization enforcement."""

    def test_unauthenticated_agent_registration_rejected(self, client: TestClient):
        """An unauthenticated request to register an agent must be rejected with 401, 403, or 422."""
        private_key, _ = _generate_keypair()
        public_key_pem = _public_key_to_pem(private_key.public_key())

        payload = {
            "agent_id": "AGT-AC-001",
            "name": "Test Agent",
            "description": "Test agent",
            "owner_type": "human",
            "owner_name": "Test Owner",
            "owner_email": "test@example.com",
            "owner_contact": None,
            "public_key_pem": public_key_pem,
            "expires_in_days": 365,
        }

        # No X-Admin-API-Key header
        response = client.post("/api/auth/register", json=payload)

        assert response.status_code in (401, 403, 422), (
            f"Expected 401, 403, or 422, got {response.status_code}: {response.text}"
        )

    def test_unauthenticated_policy_creation_rejected_even_with_owner_id(
        self, client: TestClient, db_session: Session
    ):
        """An unauthenticated request to create a spending policy must be rejected with 401, 403, or 422,
        even if X-Owner-ID is supplied."""
        private_key, _ = _generate_keypair()
        agent, _, _ = create_test_agent_with_policy(
            db_session, "AGT-AC-002", private_key
        )

        payload = {
            "per_transaction_limit_cents": 5000,
            "daily_budget_cents": 20000,
            "allowed_currencies": ["USD"],
            "allowed_merchant_ids": None,
            "blocked_merchant_ids": None,
            "expires_in_days": 365,
        }

        # Supply X-Owner-ID but NO X-Admin-API-Key
        headers = {"X-Owner-ID": "human:attacker@example.com"}
        response = client.post(
            f"/api/policies?agent_id={agent.agent_id}",
            json=payload,
            headers=headers,
        )

        assert response.status_code in (401, 403, 422), (
            f"Expected 401, 403, or 422, got {response.status_code}: {response.text}"
        )

    def test_suspended_agent_rejected_even_with_valid_signature(
        self, client: TestClient, db_session: Session
    ):
        """An authenticated agent with status SUSPENDED must not be allowed to authorize
        a payment, even with a valid Ed25519 signature."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-AC-003", private_key, status=AgentStatus.SUSPENDED
        )

        # Get a fresh nonce (should work - nonce endpoint only checks credential)
        nonce_resp = client.post(
            f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}"
        )
        assert nonce_resp.status_code == 200
        nonce = nonce_resp.json()["nonce"]

        # Create valid signed request
        payload, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=1000,
            nonce=nonce,
        )

        response = client.post("/api/authorize", json=payload)

        # Should be 403 Forbidden (agent not active)
        assert response.status_code == 403, (
            f"Expected 403 for suspended agent, got {response.status_code}: {response.text}"
        )
        # Verify no budget was reserved
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is None or usage.reserved_cents == 0

    def test_exceeds_per_transaction_limit_returns_block_no_budget(
        self, client: TestClient, db_session: Session
    ):
        """A signed request exceeding its per-transaction spending limit must return BLOCK
        and must not reserve budget."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-AC-004", private_key
        )

        # Policy has per_transaction_limit_cents=10000
        # Try to spend 15000 cents (exceeds limit)
        nonce_resp = client.post(
            f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}"
        )
        assert nonce_resp.status_code == 200
        nonce = nonce_resp.json()["nonce"]

        payload, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=15000,  # Exceeds per-transaction limit of 10000
            nonce=nonce,
        )

        response = client.post("/api/authorize", json=payload)

        assert response.status_code == 200, (
            f"Expected 200 with BLOCK decision, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert data["decision"] == "block", f"Expected BLOCK, got {data['decision']}"
        assert any("per-transaction" in v.lower() for v in data.get("policy_violations", []))

        # Verify no budget was reserved
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is None or usage.reserved_cents == 0, (
            f"Budget should not be reserved for BLOCK decision, got {usage.reserved_cents if usage else 0}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])