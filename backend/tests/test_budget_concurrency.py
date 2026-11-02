"""Concurrency tests for daily budget reservations.

These tests verify that the atomic budget reservation mechanism
correctly prevents overspending under concurrent requests.
"""

import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    AgentCredential,
    AgentStatus,
    AuthorizationDecision,
    DailyBudgetUsage,
    SpendingPolicy,
    PolicyStatus,
)
from app.services import (
    create_spending_policy,
    register_agent_credential,
    consume_nonce,
    create_nonce,
    canonical_request_string,
    compute_body_hash,
    verify_signature,
    load_public_key,
)
from app.core.config import Settings


def _generate_keypair() -> tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]:
    """Generate a test Ed25519 keypair."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


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


def create_test_agent_with_credential(
    db: Session, agent_id: str, daily_budget_cents: int = 10000, per_transaction_limit_cents: int = 5000
) -> tuple[Agent, ed25519.Ed25519PrivateKey, str]:
    """Create a test agent with credential and spending policy.

    Returns: (agent, private_key, key_id)
    """
    # Generate keypair
    private_key, public_key = _generate_keypair()
    public_key_pem = _public_key_to_pem(public_key)

    # Create agent
    agent = Agent(
        agent_id=agent_id,
        name=f"Test Agent {agent_id}",
        description="Test agent for concurrency tests",
        status=AgentStatus.ACTIVE,
        owner_type="human",
        owner_name="Test Owner",
        owner_email="test@example.com",
        owner_contact=None,
        daily_limit_usd=Decimal("0"),
        monthly_limit_usd=Decimal("0"),
    )
    db.add(agent)
    db.flush()

    # Register credential
    credential = register_agent_credential(
        db=db,
        agent=agent,
        public_key_pem=public_key_pem,
        expires_in_days=365,
    )

    # Create spending policy
    create_spending_policy(
        db=db,
        agent=agent,
        owner_id=f"human:test@example.com",
        per_transaction_limit_cents=per_transaction_limit_cents,
        daily_budget_cents=daily_budget_cents,
        allowed_currencies=["USD"],
        allowed_merchant_ids=None,
        blocked_merchant_ids=None,
        expires_in_days=365,
    )

    return agent, private_key, credential.key_id


def make_auth_request(
    client: TestClient,
    agent_id: str,
    key_id: str,
    private_key: ed25519.Ed25519PrivateKey,
    amount_cents: int,
    merchant_id: str = "MERCH-001",
    idempotency_key: str = None,
    nonce: str = None,
) -> dict:
    """Make a signed authorization request."""
    # Get nonce if not provided
    if nonce is None:
        nonce_resp = client.post(
            f"/api/auth/challenge?agent_id={agent_id}&key_id={key_id}"
        )
        assert nonce_resp.status_code == 200, f"Failed to get nonce: {nonce_resp.text}"
        nonce = nonce_resp.json()["nonce"]

    request_id = f"req-{int(time.time() * 1000)}-{idempotency_key or 'test'}"
    timestamp = datetime.utcnow()

    body_dict = {
        "request_id": request_id,
        "idempotency_key": idempotency_key,
        "agent_id": agent_id,
        "key_id": key_id,
        "nonce": nonce,
        "timestamp": timestamp.isoformat(),
        "amount_cents": amount_cents,
        "currency": "USD",
        "merchant_id": merchant_id,
        "merchant_category": "retail",
        "description": "Test transaction",
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
        "currency": "USD",
        "merchant_id": merchant_id,
        "merchant_category": "retail",
        "description": "Test transaction",
    }

    response = client.post("/api/authorize", json=payload)
    return response.json()


class TestBudgetConcurrency:
    """Tests for concurrent budget reservation."""

    def test_successful_reservation_within_budget(
        self, client: TestClient, db_session: Session
    ):
        """Test that a single request within budget succeeds."""
        agent, private_key, key_id = create_test_agent_with_credential(
            db_session, "AGT-CONCUR-001", daily_budget_cents=10000
        )

        result = make_auth_request(
            client, "AGT-CONCUR-001", key_id, private_key, amount_cents=5000
        )

        assert result["decision"] == "allow"
        assert result["daily_spent_after_cents"] == 5000
        assert result["daily_budget_remaining_cents"] == 5000

        # Verify budget row was created
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is not None
        assert usage.reserved_cents == 5000
        assert usage.daily_budget_cents == 10000

    def test_request_above_daily_budget_blocked(
        self, client: TestClient, db_session: Session
    ):
        """Test that a request exceeding daily budget is blocked."""
        agent, private_key, key_id = create_test_agent_with_credential(
            db_session, "AGT-CONCUR-002", daily_budget_cents=5000
        )

        # First request uses 3000
        result1 = make_auth_request(
            client, "AGT-CONCUR-002", key_id, private_key, amount_cents=3000
        )
        assert result1["decision"] == "allow"

        # Second request tries to use 3000 more (total 6000 > 5000)
        result2 = make_auth_request(
            client, "AGT-CONCUR-002", key_id, private_key, amount_cents=3000
        )
        assert result2["decision"] == "block"
        assert "Daily budget exceeded" in str(result2.get("policy_violations", ""))

    def test_two_simultaneous_requests_exceed_budget_one_succeeds(
        self, client: TestClient, db_session: Session
    ):
        """Test that two simultaneous requests that together exceed budget
        result in exactly one success.

        This is the core concurrency test. Each request is for 6000 cents,
        budget is 10000 cents. Only one should succeed.
        """
        # Use per_transaction_limit_cents=10000 to allow 6000 cent transactions
        agent, private_key, key_id = create_test_agent_with_credential(
            db_session, "AGT-CONCUR-003", daily_budget_cents=10000, per_transaction_limit_cents=10000
        )

        # Pre-generate nonces for both requests
        nonce1_resp = client.post(f"/api/auth/challenge?agent_id=AGT-CONCUR-003&key_id={key_id}")
        nonce2_resp = client.post(f"/api/auth/challenge?agent_id=AGT-CONCUR-003&key_id={key_id}")
        assert nonce1_resp.status_code == 200
        assert nonce2_resp.status_code == 200
        nonce1 = nonce1_resp.json()["nonce"]
        nonce2 = nonce2_resp.json()["nonce"]

        results: List[dict] = []
        errors: List[Exception] = []

        def make_request(nonce: str, idx: int):
            try:
                result = make_auth_request(
                    client,
                    "AGT-CONCUR-003",
                    key_id,
                    private_key,
                    amount_cents=6000,
                    nonce=nonce,
                    idempotency_key=f"idem-{idx}",
                )
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Run both requests concurrently
        t1 = threading.Thread(target=make_request, args=(nonce1, 1))
        t2 = threading.Thread(target=make_request, args=(nonce2, 2))

        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 2, f"Expected 2 results, got {len(results)}"

        # Exactly one should be ALLOW, one BLOCK
        allow_count = sum(1 for r in results if r["decision"] == "allow")
        block_count = sum(1 for r in results if r["decision"] == "block")

        assert allow_count == 1, f"Expected exactly 1 ALLOW, got {allow_count}"
        assert block_count == 1, f"Expected exactly 1 BLOCK, got {block_count}"

        # Verify final budget state
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is not None
        # Only one 6000 reservation should exist
        assert usage.reserved_cents == 6000
        assert usage.daily_budget_cents == 10000

    def test_duplicate_idempotency_key_does_not_reserve_twice(
        self, client: TestClient, db_session: Session
    ):
        """Test that repeating the same idempotency key returns the same
        decision without reserving budget twice."""
        agent, private_key, key_id = create_test_agent_with_credential(
            db_session, "AGT-CONCUR-004", daily_budget_cents=10000
        )

        idempotency_key = "idem-duplicate-test"

        # First request
        result1 = make_auth_request(
            client, "AGT-CONCUR-004", key_id, private_key,
            amount_cents=4000, idempotency_key=idempotency_key
        )
        assert result1["decision"] == "allow"

        # Second request with same idempotency key
        result2 = make_auth_request(
            client, "AGT-CONCUR-004", key_id, private_key,
            amount_cents=4000, idempotency_key=idempotency_key
        )
        assert result2["decision"] == "allow"
        assert result2["request_id"] == result1["request_id"]

        # Budget should only be reserved once (4000)
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        assert usage is not None
        assert usage.reserved_cents == 4000

    def test_failure_rolls_back_reservation(
        self, client: TestClient, db_session: Session
    ):
        """Test that a failure during authorization (e.g., invalid signature)
        does not leave a budget reservation."""
        agent, private_key, key_id = create_test_agent_with_credential(
            db_session, "AGT-CONCUR-005", daily_budget_cents=10000
        )

        # Make a request with invalid signature
        nonce_resp = client.post(f"/api/auth/challenge?agent_id=AGT-CONCUR-005&key_id={key_id}")
        assert nonce_resp.status_code == 200
        nonce = nonce_resp.json()["nonce"]

        request_id = f"req-{int(time.time() * 1000)}-invalid-sig"
        timestamp = datetime.utcnow()

        body_dict = {
            "request_id": request_id,
            "idempotency_key": "idem-invalid-sig",
            "agent_id": "AGT-CONCUR-005",
            "key_id": key_id,
            "nonce": nonce,
            "timestamp": timestamp.isoformat(),
            "amount_cents": 5000,
            "currency": "USD",
            "merchant_id": "MERCH-001",
            "merchant_category": "retail",
            "description": "Test transaction",
        }
        body_hash = compute_body_hash(body_dict)

        canonical = canonical_request_string(
            method="POST",
            path="/api/authorize",
            timestamp=timestamp.isoformat(),
            nonce=nonce,
            body_hash=body_hash,
        )

        # Sign with WRONG private key
        wrong_private_key, _ = _generate_keypair()
        wrong_signature = _sign_request(wrong_private_key, canonical)

        payload = {
            "request_id": request_id,
            "idempotency_key": "idem-invalid-sig",
            "agent_id": "AGT-CONCUR-005",
            "key_id": key_id,
            "nonce": nonce,
            "timestamp": timestamp.isoformat(),
            "signature": wrong_signature,
            "amount_cents": 5000,
            "currency": "USD",
            "merchant_id": "MERCH-001",
            "merchant_category": "retail",
            "description": "Test transaction",
        }

        response = client.post("/api/authorize", json=payload)
        assert response.status_code == 401  # Unauthorized due to invalid signature

        # Budget should NOT be reserved
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        # Row might not even exist, or if it does, reserved_cents should be 0
        if usage:
            assert usage.reserved_cents == 0


    def test_failed_policy_check_does_not_reserve(
        self, client: TestClient, db_session: Session
    ):
        """Test that a request failing policy checks (e.g., wrong currency)
        does not reserve budget."""
        agent, private_key, key_id = create_test_agent_with_credential(
            db_session, "AGT-CONCUR-006", daily_budget_cents=10000
        )

        # Request with disallowed currency (EUR not in allowed_currencies)
        nonce_resp = client.post(f"/api/auth/challenge?agent_id=AGT-CONCUR-006&key_id={key_id}")
        assert nonce_resp.status_code == 200
        nonce = nonce_resp.json()["nonce"]

        request_id = f"req-{int(time.time() * 1000)}-wrong-currency"
        timestamp = datetime.utcnow()

        body_dict = {
            "request_id": request_id,
            "idempotency_key": "idem-wrong-currency",
            "agent_id": "AGT-CONCUR-006",
            "key_id": key_id,
            "nonce": nonce,
            "timestamp": timestamp.isoformat(),
            "amount_cents": 5000,
            "currency": "EUR",  # Not allowed!
            "merchant_id": "MERCH-001",
            "merchant_category": "retail",
            "description": "Test transaction",
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
            "idempotency_key": "idem-wrong-currency",
            "agent_id": "AGT-CONCUR-006",
            "key_id": key_id,
            "nonce": nonce,
            "timestamp": timestamp.isoformat(),
            "signature": signature,
            "amount_cents": 5000,
            "currency": "EUR",
            "merchant_id": "MERCH-001",
            "merchant_category": "retail",
            "description": "Test transaction",
        }

        response = client.post("/api/authorize", json=payload)
        # Should be blocked due to currency violation
        assert response.status_code == 200
        result = response.json()
        assert result["decision"] == "block"
        assert any("currency" in str(v).lower() for v in result.get("policy_violations", []))

        # Budget should NOT be reserved for BLOCK decisions
        usage = db_session.query(DailyBudgetUsage).filter(
            DailyBudgetUsage.agent_id == agent.id
        ).first()
        if usage:
            assert usage.reserved_cents == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])