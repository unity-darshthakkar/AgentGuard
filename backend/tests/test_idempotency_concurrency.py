"""Concurrency tests for idempotency key handling.

These tests verify that the authorization endpoint correctly handles
concurrent requests with the same idempotency key.
"""

import threading
import time
from datetime import datetime
from typing import List, Optional

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Agent,
    AgentCredential,
    AgentStatus,
    AuthorizationDecision,
    AuthorizationDecisionRecord,
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
from app.core.database import Base, get_db
from app.main import create_app


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
        daily_limit_usd=0,
        monthly_limit_usd=0,
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
    merchant_category: str = "retail",
    description: str = "Test transaction",
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
        "currency": "USD",
        "merchant_id": merchant_id,
        "merchant_category": merchant_category,
        "description": description,
    }

    response = client.post("/api/authorize", json=payload)
    return {"status_code": response.status_code, "data": response.json() if response.status_code < 500 else None, "error": response.text if response.status_code >= 500 else None}


class TestIdempotencyConcurrency:
    """Tests for concurrent idempotency key handling."""

    def test_same_idempotency_key_same_intent_concurrent_requests(
        self, client: TestClient, db_session: Session
    ):
        """
        Test A: Two simultaneous signed requests with the SAME idempotency key
        and SAME payment intent but different fresh nonces.

        Expected:
        - Exactly one authorization decision record.
        - Exactly one budget reservation.
        - Both requests receive a controlled result: original ALLOW or a documented retryable response.
        - No unhandled 500 errors.
        """
        agent, private_key, key_id = create_test_agent_with_credential(
            db_session, "AGT-IDEMP-001", daily_budget_cents=10000, per_transaction_limit_cents=10000
        )

        idempotency_key = "idem-concurrent-same-intent"

        # Pre-generate two different nonces
        nonce1_resp = client.post(f"/api/auth/challenge?agent_id=AGT-IDEMP-001&key_id={key_id}")
        nonce2_resp = client.post(f"/api/auth/challenge?agent_id=AGT-IDEMP-001&key_id={key_id}")
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
                    "AGT-IDEMP-001",
                    key_id,
                    private_key,
                    amount_cents=5000,
                    merchant_id="MERCH-001",
                    idempotency_key=idempotency_key,
                    nonce=nonce,
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

        # Check results - no 500 errors
        for r in results:
            assert r["status_code"] != 500, f"Got 500 error: {r}"

        # Both should succeed (200) with ALLOW decision (one original, one cached retry)
        # This is the correct behavior for idempotent retries
        success_count = sum(1 for r in results if r["status_code"] == 200)
        allow_count = sum(1 for r in results if r["status_code"] == 200 and r["data"]["decision"] == "allow")
        assert success_count == 2, f"Expected both requests to succeed, got {success_count}"
        assert allow_count == 2, f"Expected both requests to return ALLOW, got {allow_count}"

        # Both should return the same request_id (the first one's)
        request_ids = {r["data"]["request_id"] for r in results if r["status_code"] == 200}
        assert len(request_ids) == 1, f"Expected same request_id for both, got {request_ids}"

        # Verify database state - exactly one authorization decision record
        records = db_session.execute(
            select(AuthorizationDecisionRecord).where(
                AuthorizationDecisionRecord.idempotency_key == idempotency_key
            )
        ).scalars().all()
        assert len(records) == 1, f"Expected 1 authorization record, got {len(records)}"

        # Verify budget reserved only once
        usage = db_session.execute(
            select(DailyBudgetUsage).where(DailyBudgetUsage.agent_id == agent.id)
        ).scalar_one_or_none()
        assert usage is not None
        assert usage.reserved_cents == 5000, f"Expected 5000 reserved cents, got {usage.reserved_cents}"

    def test_same_idempotency_key_different_intent_concurrent_requests(
        self, client: TestClient, db_session: Session
    ):
        """
        Test B: Two simultaneous signed requests with the SAME idempotency key
        but DIFFERENT payment intents.

        Expected:
        - At most one successful authorization.
        - Conflicting request returns HTTP 409, including after resolving a database uniqueness race.
        - No double budget reservation.
        - No unhandled 500 errors.
        """
        agent, private_key, key_id = create_test_agent_with_credential(
            db_session, "AGT-IDEMP-002", daily_budget_cents=10000, per_transaction_limit_cents=10000
        )

        idempotency_key = "idem-concurrent-different-intent"

        # Pre-generate two different nonces
        nonce1_resp = client.post(f"/api/auth/challenge?agent_id=AGT-IDEMP-002&key_id={key_id}")
        nonce2_resp = client.post(f"/api/auth/challenge?agent_id=AGT-IDEMP-002&key_id={key_id}")
        assert nonce1_resp.status_code == 200
        assert nonce2_resp.status_code == 200
        nonce1 = nonce1_resp.json()["nonce"]
        nonce2 = nonce2_resp.json()["nonce"]

        results: List[dict] = []
        errors: List[Exception] = []

        def make_request(nonce: str, idx: int, merchant_id: str):
            try:
                result = make_auth_request(
                    client,
                    "AGT-IDEMP-002",
                    key_id,
                    private_key,
                    amount_cents=5000,
                    merchant_id=merchant_id,
                    merchant_category="retail",
                    description="Test transaction",
                    idempotency_key=idempotency_key,
                    nonce=nonce,
                )
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Run both requests concurrently with DIFFERENT merchant IDs (different intent)
        t1 = threading.Thread(target=make_request, args=(nonce1, 1, "MERCH-001"))
        t2 = threading.Thread(target=make_request, args=(nonce2, 2, "MERCH-002"))

        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 2, f"Expected 2 results, got {len(results)}"

        # Check results - no 500 errors
        for r in results:
            assert r["status_code"] != 500, f"Got 500 error: {r}"

        # One should succeed (200 with ALLOW or BLOCK), one should get 409 Conflict
        success_count = sum(1 for r in results if r["status_code"] == 200)
        conflict_count = sum(1 for r in results if r["status_code"] == 409)

        assert success_count <= 1, f"Expected at most 1 success, got {success_count}"
        assert conflict_count >= 1, f"Expected at least 1 conflict (409), got {conflict_count}"

        # Verify database state - at most one authorization decision record
        records = db_session.execute(
            select(AuthorizationDecisionRecord).where(
                AuthorizationDecisionRecord.idempotency_key == idempotency_key
            )
        ).scalars().all()
        assert len(records) <= 1, f"Expected at most 1 authorization record, got {len(records)}"

        # Verify budget reserved at most once
        usage = db_session.execute(
            select(DailyBudgetUsage).where(DailyBudgetUsage.agent_id == agent.id)
        ).scalar_one_or_none()
        if usage:
            assert usage.reserved_cents <= 5000, f"Expected at most 5000 reserved cents, got {usage.reserved_cents}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])