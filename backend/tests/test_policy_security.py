"""Authorization policy security regression tests."""

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
    revoke_policy,
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
    per_transaction_limit_cents: int = 10000,
    daily_budget_cents: int = 50000,
    allowed_currencies: list = None,
    allowed_merchant_ids: list = None,
    blocked_merchant_ids: list = None,
    expires_in_days: int = 365,
) -> Tuple[Agent, ed25519.Ed25519PrivateKey, str]:
    """Create a test agent with credential and spending policy."""
    public_key_pem = _public_key_to_pem(private_key.public_key())

    agent = Agent(
        agent_id=agent_id,
        name=f"Test Agent {agent_id}",
        description="Test agent for policy security tests",
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
        per_transaction_limit_cents=per_transaction_limit_cents,
        daily_budget_cents=daily_budget_cents,
        allowed_currencies=allowed_currencies or ["USD"],
        allowed_merchant_ids=allowed_merchant_ids,
        blocked_merchant_ids=blocked_merchant_ids,
        expires_in_days=expires_in_days,
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


class TestPolicySecurity:
    """Tests for authorization policy enforcement boundaries."""

    def test_merchant_allowlist_enforced(self, client: TestClient, db_session: Session):
        """An otherwise valid signed payment request to a merchant not in the
        policy's approved merchant list must return BLOCK, without reserving budget."""
        private_key, _ = _generate_keypair()
        # Policy only allows MERCH-APPROVED
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-POL-001", private_key,
            allowed_merchant_ids=["MERCH-APPROVED"],
        )

        nonce_resp = client.post(
            f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}"
        )
        assert nonce_resp.status_code == 200
        nonce = nonce_resp.json()["nonce"]

        # Request to merchant NOT in allowlist
        payload, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=1000,
            merchant_id="MERCH-BLOCKED",  # Not in allowlist
            nonce=nonce,
        )

        response = client.post("/api/authorize", json=payload)

        assert response.status_code == 200, (
            f"Expected 200 with BLOCK, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert data["decision"] == "block", f"Expected BLOCK, got {data['decision']}"
        assert any("merchant" in v.lower() for v in data.get("policy_violations", []))

        # Verify no budget reserved
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is None or usage.reserved_cents == 0, (
            f"Budget should not be reserved for BLOCK decision"
        )

    def test_currency_restriction_enforced(self, client: TestClient, db_session: Session):
        """An otherwise valid signed request using a currency outside the policy's
        allowed currencies must return BLOCK, without reserving budget."""
        private_key, _ = _generate_keypair()
        # Policy only allows USD
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-POL-002", private_key,
            allowed_currencies=["USD"],
        )

        nonce_resp = client.post(
            f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}"
        )
        assert nonce_resp.status_code == 200
        nonce = nonce_resp.json()["nonce"]

        # Request with EUR (not in allowed currencies)
        payload, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=1000,
            currency="EUR",  # Not allowed
            nonce=nonce,
        )

        response = client.post("/api/authorize", json=payload)

        assert response.status_code == 200, (
            f"Expected 200 with BLOCK, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert data["decision"] == "block", f"Expected BLOCK, got {data['decision']}"
        assert any("currency" in v.lower() for v in data.get("policy_violations", []))

        # Verify no budget reserved
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is None or usage.reserved_cents == 0, (
            f"Budget should not be reserved for BLOCK decision"
        )

    def test_expired_policy_denied(self, client: TestClient, db_session: Session):
        """A valid signed request associated with an expired policy must be denied,
        without reserving budget."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-POL-003", private_key,
            expires_in_days=-1,  # Already expired
        )

        # Verify policy is expired
        policy = db_session.query(SpendingPolicy).filter(
            SpendingPolicy.agent_id == agent.id
        ).first()
        assert policy is not None
        assert policy.status == PolicyStatus.EXPIRED or policy.expires_at < datetime.utcnow()

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

        assert response.status_code == 200, (
            f"Expected 200 with BLOCK, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert data["decision"] == "block", f"Expected BLOCK, got {data['decision']}"
        assert any("expired" in v.lower() or "policy" in v.lower() for v in data.get("policy_violations", []))

        # Verify no budget reserved
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is None or usage.reserved_cents == 0, (
            f"Budget should not be reserved for BLOCK decision"
        )

    def test_conflicting_idempotency_key_rejected(self, client: TestClient, db_session: Session):
        """After a successfully authorized request, a new validly signed payment request
        with the same idempotency key but a different amount or merchant must be rejected
        with HTTP 409 Conflict and must not reserve additional budget."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-POL-004", private_key,
        )

        idempotency_key = "idem-conflict-test"

        # Get first nonce from challenge endpoint
        nonce_resp1 = client.post(
            f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}"
        )
        assert nonce_resp1.status_code == 200
        nonce1 = nonce_resp1.json()["nonce"]

        # First request: $10.00 to MERCH-A
        payload1, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=1000,
            merchant_id="MERCH-A",
            nonce=nonce1,
            idempotency_key=idempotency_key,
        )

        response1 = client.post("/api/authorize", json=payload1)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["decision"] == "allow"
        first_request_id = data1["request_id"]

        # Verify budget reserved: 1000 cents
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is not None
        assert usage.reserved_cents == 1000

        # Get second nonce from challenge endpoint
        nonce_resp2 = client.post(
            f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}"
        )
        assert nonce_resp2.status_code == 200
        nonce2 = nonce_resp2.json()["nonce"]

        # Second request: SAME idempotency key, DIFFERENT amount ($20.00) and merchant
        payload2, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=2000,  # Different amount!
            merchant_id="MERCH-B",  # Different merchant!
            nonce=nonce2,
            idempotency_key=idempotency_key,  # Same idempotency key!
        )

        response2 = client.post("/api/authorize", json=payload2)

        # MUST return 409 Conflict for conflicting intent
        assert response2.status_code == 409, (
            f"Expected 409 Conflict for conflicting idempotency key, "
            f"got {response2.status_code}: {response2.text}"
        )
        data2 = response2.json()
        assert "idempotency" in data2.get("detail", "").lower() or \
               "different" in data2.get("detail", "").lower()

        # Verify NO additional budget reserved (still 1000, not 3000)
        db_session.expire_all()
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is not None
        assert usage.reserved_cents == 1000, (
            f"Budget should not increase on conflicting idempotency key, got {usage.reserved_cents}"
        )

    def test_identical_retry_does_not_reserve_twice(self, client: TestClient, db_session: Session):
        """A retry with the SAME idempotency key and SAME intent (using a new valid nonce)
        must return the original decision without reserving budget again."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-POL-005", private_key,
        )

        idempotency_key = "idem-retry-test"

        # First request
        nonce_resp1 = client.post(
            f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}"
        )
        assert nonce_resp1.status_code == 200
        nonce1 = nonce_resp1.json()["nonce"]

        payload1, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=1000,
            merchant_id="MERCH-A",
            nonce=nonce1,
            idempotency_key=idempotency_key,
        )

        response1 = client.post("/api/authorize", json=payload1)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["decision"] == "allow"
        first_request_id = data1["request_id"]

        # Verify budget reserved: 1000 cents
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is not None
        assert usage.reserved_cents == 1000

        # Get a NEW nonce (simulating a legitimate retry)
        nonce_resp2 = client.post(
            f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}"
        )
        assert nonce_resp2.status_code == 200
        nonce2 = nonce_resp2.json()["nonce"]

        # Second request: SAME idempotency key, SAME intent, NEW nonce
        payload2, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=1000,  # Same amount
            merchant_id="MERCH-A",  # Same merchant
            nonce=nonce2,  # New nonce
            idempotency_key=idempotency_key,  # Same idempotency key
        )

        response2 = client.post("/api/authorize", json=payload2)

        # Should return original decision (idempotent replay)
        assert response2.status_code == 200, (
            f"Expected 200 for identical retry, got {response2.status_code}: {response2.text}"
        )
        data2 = response2.json()
        assert data2["request_id"] == first_request_id, (
            "Should return original request_id for idempotent replay"
        )
        assert data2["decision"] == "allow"

        # Verify NO additional budget reserved (still 1000)
        db_session.expire_all()
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is not None
        assert usage.reserved_cents == 1000, (
            f"Budget should not increase on identical retry, got {usage.reserved_cents}"
        )

    def test_identical_retry_nonce_cannot_be_reused(self, client: TestClient, db_session: Session):
        """The nonce used by a successful identical retry must be consumed and cannot
        be reused for another request (even with same idempotency key and intent)."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-POL-006", private_key,
        )

        idempotency_key = "idem-retry-nonce-reuse"

        # First request
        nonce_resp1 = client.post(
            f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}"
        )
        assert nonce_resp1.status_code == 200
        nonce1 = nonce_resp1.json()["nonce"]

        payload1, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=1000,
            merchant_id="MERCH-A",
            nonce=nonce1,
            idempotency_key=idempotency_key,
        )

        response1 = client.post("/api/authorize", json=payload1)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["decision"] == "allow"

        # Get a NEW nonce (simulating a legitimate retry)
        nonce_resp2 = client.post(
            f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}"
        )
        assert nonce_resp2.status_code == 200
        nonce2 = nonce_resp2.json()["nonce"]

        # Second request: SAME idempotency key, SAME intent, NEW nonce (retry)
        payload2, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=1000,
            merchant_id="MERCH-A",
            nonce=nonce2,
            idempotency_key=idempotency_key,
        )

        response2 = client.post("/api/authorize", json=payload2)
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["decision"] == "allow"
        assert data2["request_id"] == data1["request_id"]

        # NOW try to REUSE the retry nonce (nonce2) with a DIFFERENT idempotency key
        # This should fail because nonce2 was already consumed in the retry
        nonce_resp3 = client.post(
            f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}"
        )
        assert nonce_resp3.status_code == 200
        nonce3 = nonce_resp3.json()["nonce"]

        payload3, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=1000,
            merchant_id="MERCH-A",
            nonce=nonce2,  # REUSE nonce2 - should fail!
            idempotency_key="idem-different",  # Different idempotency key
        )

        response3 = client.post("/api/authorize", json=payload3)
        # Should be 401/403 because nonce2 was already consumed
        assert response3.status_code in (401, 403), (
            f"Expected 401 or 403 for reused retry nonce, got {response3.status_code}: {response3.text}"
        )

        # Budget should still be 1000
        db_session.expire_all()
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is not None
        assert usage.reserved_cents == 1000, (
            f"Budget should not increase on replayed retry nonce, got {usage.reserved_cents}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])