"""Ed25519 signature verification regression tests."""

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
    create_nonce,
    compute_body_hash,
    canonical_request_string,
    revoke_credential,
)
from app.core.config import Settings


def _generate_keypair() -> Tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]:
    """Generate a test Ed25519 keypair."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    return private_key, private_key.public_key()


def _private_key_to_pem(private_key: ed25519.Ed25519PrivateKey) -> str:
    """Convert private key to PEM string."""
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


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
) -> Tuple[Agent, ed25519.Ed25519PrivateKey, str]:
    """Create a test agent with credential and spending policy."""
    public_key_pem = _public_key_to_pem(private_key.public_key())

    agent = Agent(
        agent_id=agent_id,
        name=f"Test Agent {agent_id}",
        description="Test agent for signature tests",
        status=AgentStatus.ACTIVE,
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
) -> Tuple[dict, str]:
    """Create a signed authorization request payload."""
    if nonce is None:
        nonce = f"nonce-{int(time.time() * 1000)}"

    if request_id is None:
        request_id = f"req-{int(time.time() * 1000)}"

    if idempotency_key is None:
        idempotency_key = f"idem-{int(time.time() * 1000)}"

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


class TestAgentSignature:
    """Tests for Ed25519 signature verification in authorization endpoint."""

    def test_valid_signed_request_succeeds(self, client: TestClient, db_session: Session):
        """A valid Ed25519-signed payment authorization request succeeds with decision ALLOW."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-SIG-001", private_key
        )

        # Get a fresh nonce from the challenge endpoint
        nonce_resp = client.post(
            f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}"
        )
        assert nonce_resp.status_code == 200
        nonce = nonce_resp.json()["nonce"]

        payload, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=1000,
            nonce=nonce,
        )

        response = client.post("/api/authorize", json=payload)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["decision"] == "allow", f"Expected ALLOW, got {data['decision']}: {data}"

    def test_wrong_private_key_rejected(self, client: TestClient, db_session: Session):
        """A request signed using the wrong private key is rejected with HTTP 401 or 403."""
        private_key, _ = _generate_keypair()
        wrong_private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-SIG-002", private_key
        )

        # Get a fresh nonce
        nonce_resp = client.post(
            f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}"
        )
        assert nonce_resp.status_code == 200
        nonce = nonce_resp.json()["nonce"]

        # Sign with WRONG private key
        payload, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=wrong_private_key,  # Wrong key!
            amount_cents=1000,
            nonce=nonce,
        )

        response = client.post("/api/authorize", json=payload)

        assert response.status_code in (401, 403), (
            f"Expected 401 or 403, got {response.status_code}: {response.text}"
        )
        # Verify no budget was consumed
        from app.models import DailyBudgetUsage
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is None or usage.reserved_cents == 0

    def test_modified_amount_invalidates_signature(self, client: TestClient, db_session: Session):
        """Modifying the payment amount after signing causes signature verification to fail."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-SIG-003", private_key
        )

        # Get a fresh nonce
        nonce_resp = client.post(
            f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}"
        )
        assert nonce_resp.status_code == 200
        nonce = nonce_resp.json()["nonce"]

        # Create a valid payload
        payload, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=1000,  # Original amount: 1000 cents
            nonce=nonce,
        )

        # TAMPER: Change amount_cents from 1000 to 5000 AFTER signing
        payload["amount_cents"] = 5000

        response = client.post("/api/authorize", json=payload)

        assert response.status_code in (401, 403), (
            f"Expected 401 or 403, got {response.status_code}: {response.text}"
        )
        # Verify no budget was consumed
        from app.models import DailyBudgetUsage
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is None or usage.reserved_cents == 0

    def test_replay_nonce_rejected(self, client: TestClient, db_session: Session):
        """Reusing an already consumed nonce must be rejected and must not reserve additional budget."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-SIG-004", private_key
        )

        # Get a fresh nonce
        nonce_resp = client.post(
            f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}"
        )
        assert nonce_resp.status_code == 200
        nonce = nonce_resp.json()["nonce"]

        # First request - should succeed
        payload, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=1000,
            nonce=nonce,
        )

        response1 = client.post("/api/authorize", json=payload)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["decision"] == "allow"

        # Verify budget was reserved for first request
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is not None
        assert usage.reserved_cents == 1000

        # Second request with SAME nonce - should be rejected (replay)
        payload2, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=2000,  # Different amount
            nonce=nonce,  # Same nonce - replay attempt
        )

        response2 = client.post("/api/authorize", json=payload2)

        assert response2.status_code in (401, 403), (
            f"Expected 401 or 403 for replay, got {response2.status_code}: {response2.text}"
        )

        # Verify NO additional budget was reserved
        db_session.expire_all()
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is not None
        assert usage.reserved_cents == 1000, "Budget should not increase on replay"

    def test_revoked_credential_rejected(self, client: TestClient, db_session: Session):
        """An agent with a revoked credential must be unable to authorize a payment."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-SIG-005", private_key
        )

        # Get a fresh nonce WHILE credential is still active
        nonce_resp = client.post(
            f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}"
        )
        assert nonce_resp.status_code == 200
        nonce = nonce_resp.json()["nonce"]

        # NOW revoke the credential
        credential = db_session.query(AgentCredential).filter(
            AgentCredential.agent_id == agent.id,
            AgentCredential.key_id == key_id,
        ).first()
        assert credential is not None

        revoke_credential(
            db=db_session,
            credential=credential,
            revoked_by="admin",
            reason="Test revocation",
        )

        # Try to authorize with the previously issued nonce and revoked credential
        payload, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=1000,
            nonce=nonce,
        )

        response = client.post("/api/authorize", json=payload)

        assert response.status_code in (401, 403), (
            f"Expected 401 or 403 for revoked credential, got {response.status_code}: {response.text}"
        )
        # Verify no budget was consumed
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is None or usage.reserved_cents == 0

    def test_expired_timestamp_rejected(self, client: TestClient, db_session: Session):
        """A correctly signed request with an expired timestamp must be rejected."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-SIG-006", private_key
        )

        # Get a fresh nonce
        nonce_resp = client.post(
            f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}"
        )
        assert nonce_resp.status_code == 200
        nonce = nonce_resp.json()["nonce"]

        # Create a payload with timestamp > 2 minutes old (expired)
        # The server accepts ±120 seconds tolerance
        old_timestamp = datetime.utcnow() - timedelta(minutes=5)

        body_dict = {
            "request_id": f"req-{int(time.time() * 1000)}",
            "idempotency_key": f"idem-{int(time.time() * 1000)}",
            "agent_id": agent.agent_id,
            "key_id": key_id,
            "nonce": nonce,
            "timestamp": old_timestamp.isoformat(),
            "amount_cents": 1000,
            "currency": "USD",
            "merchant_id": "MERCH-001",
            "merchant_category": "retail",
            "description": "Test transaction",
        }
        body_hash = compute_body_hash(body_dict)

        canonical = canonical_request_string(
            method="POST",
            path="/api/authorize",
            timestamp=old_timestamp.isoformat(),
            nonce=nonce,
            body_hash=body_hash,
        )

        signature = _sign_request(private_key, canonical)

        payload = {
            "request_id": body_dict["request_id"],
            "idempotency_key": body_dict["idempotency_key"],
            "agent_id": agent.agent_id,
            "key_id": key_id,
            "nonce": nonce,
            "timestamp": old_timestamp.isoformat(),
            "signature": signature,
            "amount_cents": 1000,
            "currency": "USD",
            "merchant_id": "MERCH-001",
            "merchant_category": "retail",
            "description": "Test transaction",
        }

        response = client.post("/api/authorize", json=payload)

        assert response.status_code == 401, (
            f"Expected 401 for expired timestamp, got {response.status_code}: {response.text}"
        )
        # Verify no budget was consumed
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is None or usage.reserved_cents == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])