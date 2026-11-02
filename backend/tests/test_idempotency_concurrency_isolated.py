"""Concurrency tests for idempotency key handling using isolated file-backed SQLite databases.

These tests verify that the authorization endpoint correctly handles
concurrent requests with the same idempotency key using separate database connections.
"""

import threading
import time
import tempfile
import os
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
    create_nonce,
    canonical_request_string,
    compute_body_hash,
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


def setup_test_database(db_path: str) -> tuple:
    """Set up a test database with schema."""
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return engine


def create_test_agent_in_db(engine, agent_id: str, daily_budget_cents: int = 10000, per_transaction_limit_cents: int = 10000):
    """Create a test agent with credential and policy in a specific database."""
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = SessionLocal()
    try:
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
        db.commit()

        return agent.id, private_key, credential.key_id
    finally:
        db.close()


def make_auth_request_direct(
    engine,
    agent_id: str,
    key_id: str,
    private_key: ed25519.Ed25519PrivateKey,
    amount_cents: int,
    merchant_id: str = "MERCH-001",
    merchant_category: str = "retail",
    description: str = "Test transaction",
    idempotency_key: str = None,
    nonce: str = None,
    request_suffix: str = "",
) -> dict:
    """Make a signed authorization request using a direct engine connection."""
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = SessionLocal()

    try:
        # Get nonce if not provided
        if nonce is None:
            # We need to create a nonce directly
            from app.services.auth import create_nonce
            nonce, _ = create_nonce(db, agent_id=agent_id)

        # Use a unique request_id with thread-specific suffix to avoid collisions
        request_id = f"req-{int(time.time() * 1000)}-{idempotency_key or 'test'}-{request_suffix}"
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

        # Now make the actual HTTP request through the API
        # We'll use a TestClient with this specific engine
        test_settings = Settings(
            database_url=f"sqlite:///{engine.url.database}",
            cors_origins=["http://localhost:5173"],
            debug=True,
        )

        app = create_app()

        def override_get_db():
            try:
                yield db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as test_client:
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

            response = test_client.post("/api/authorize", json=payload)
            return {"status_code": response.status_code, "data": response.json() if response.status_code < 500 else None, "error": response.text if response.status_code >= 500 else None}
    finally:
        db.close()


class TestIdempotencyConcurrencyIsolated:
    """Tests for concurrent idempotency key handling with isolated database connections."""

    def test_same_idempotency_key_same_intent_concurrent_requests(self):
        """
        Test A: Two simultaneous signed requests with the SAME idempotency key
        and SAME payment intent but different fresh nonces.

        Uses isolated file-backed SQLite database with separate connections.
        """
        # Create a temporary database file
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

        try:
            engine = setup_test_database(db_path)

            # Create test agent
            agent_id = "AGT-IDEMP-001"
            agent_db_id, private_key, key_id = create_test_agent_in_db(
                engine, agent_id, daily_budget_cents=10000, per_transaction_limit_cents=10000
            )

            idempotency_key = "idem-concurrent-same-intent"

            # Pre-generate two different nonces in the database
            SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
            db = SessionLocal()
            try:
                nonce1, _ = create_nonce(db, agent_db_id)
                nonce2, _ = create_nonce(db, agent_db_id)
                db.commit()
            finally:
                db.close()

            results: List[dict] = []
            errors: List[Exception] = []

            def make_request(nonce: str, idx: int):
                try:
                    result = make_auth_request_direct(
                        engine,
                        agent_id,
                        key_id,
                        private_key,
                        amount_cents=5000,
                        merchant_id="MERCH-001",
                        idempotency_key=idempotency_key,
                        nonce=nonce,
                        request_suffix=str(idx),
                    )
                    results.append(result)
                except Exception as e:
                    errors.append(e)

            # Run both requests concurrently with SEPARATE connections
            t1 = threading.Thread(target=make_request, args=(nonce1, 1))
            t2 = threading.Thread(target=make_request, args=(nonce2, 2))

            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

            # Check results
            assert len(errors) == 0, f"Errors occurred: {errors}"
            assert len(results) == 2, f"Expected 2 results, got {len(results)}"

            # No 500 errors
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
            db = SessionLocal()
            try:
                records = db.execute(
                    select(AuthorizationDecisionRecord).where(
                        AuthorizationDecisionRecord.idempotency_key == idempotency_key
                    )
                ).scalars().all()
                assert len(records) == 1, f"Expected 1 authorization record, got {len(records)}"

                # Verify budget reserved only once
                usage = db.execute(
                    select(DailyBudgetUsage).where(DailyBudgetUsage.agent_id == agent_db_id)
                ).scalar_one_or_none()
                assert usage is not None
                assert usage.reserved_cents == 5000, f"Expected 5000 reserved cents, got {usage.reserved_cents}"
            finally:
                db.close()

        finally:
            engine.dispose()
            os.unlink(db_path)

    def test_same_idempotency_key_different_intent_concurrent_requests(self):
        """
        Test B: Two simultaneous signed requests with the SAME idempotency key
        but DIFFERENT payment intents.

        Uses isolated file-backed SQLite database with separate connections.
        """
        # Create a temporary database file
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

        try:
            engine = setup_test_database(db_path)

            # Create test agent
            agent_id = "AGT-IDEMP-002"
            agent_db_id, private_key, key_id = create_test_agent_in_db(
                engine, agent_id, daily_budget_cents=10000, per_transaction_limit_cents=10000
            )

            idempotency_key = "idem-concurrent-different-intent"

            # Pre-generate two different nonces in the database
            SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
            db = SessionLocal()
            try:
                nonce1, _ = create_nonce(db, agent_db_id)
                nonce2, _ = create_nonce(db, agent_db_id)
                db.commit()
            finally:
                db.close()

            results: List[dict] = []
            errors: List[Exception] = []

            def make_request(nonce: str, idx: int, merchant_id: str):
                try:
                    result = make_auth_request_direct(
                        engine,
                        agent_id,
                        key_id,
                        private_key,
                        amount_cents=5000,
                        merchant_id=merchant_id,
                        merchant_category="retail",
                        description="Test transaction",
                        idempotency_key=idempotency_key,
                        nonce=nonce,
                        request_suffix=str(idx),
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
            db = SessionLocal()
            try:
                records = db.execute(
                    select(AuthorizationDecisionRecord).where(
                        AuthorizationDecisionRecord.idempotency_key == idempotency_key
                    )
                ).scalars().all()
                assert len(records) <= 1, f"Expected at most 1 authorization record, got {len(records)}"

                # Verify budget reserved at most once
                usage = db.execute(
                    select(DailyBudgetUsage).where(DailyBudgetUsage.agent_id == agent_db_id)
                ).scalar_one_or_none()
                if usage:
                    assert usage.reserved_cents <= 5000, f"Expected at most 5000 reserved cents, got {usage.reserved_cents}"
            finally:
                db.close()

        finally:
            engine.dispose()
            os.unlink(db_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])