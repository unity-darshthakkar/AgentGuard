"""Concurrency regression test for simultaneous capture and release of the same reservation."""

import json
import os
import tempfile
import threading
import time
from datetime import datetime
from decimal import Decimal

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Agent,
    AgentStatus,
    AuthorizationDecision,
    AuthorizationDecisionRecord,
    AuthorizationReservation,
    DailyBudgetUsage,
    ReservationStatus,
    SpendingPolicy,
    PolicyStatus,
)
from app.services import (
    create_spending_policy,
    register_agent_credential,
    capture_reservation,
    release_reservation,
    get_reservation_by_auth_decision,
    get_active_policy,
)
from app.services.auth import _get_usage_date, create_reservation


def _generate_keypair() -> tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]:
    """Generate a test Ed25519 keypair."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


def _public_key_to_pem(public_key: ed25519.Ed25519PublicKey) -> str:
    """Convert public key to PEM string."""
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def test_concurrent_capture_and_release_race():
    """Test: Concurrent capture and release against ONE RESERVED reservation.

    Uses a temporary file-backed SQLite database with two independent sessions
    and a barrier to coordinate concurrent execution.

    Verify:
    - Exactly one transition succeeds.
    - Final status is either CAPTURED or RELEASED.
    - Budget changes happen exactly once.
    - No negative reserved_cents.
    - No double capture or double release.
    - No unhandled database exceptions.
    """
    # Create a temporary file-backed SQLite database
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_url = f"sqlite:///{db_path}"

    engine = None
    try:
        engine = create_engine(db_url, connect_args={"check_same_thread": False}, echo=False)

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        from app.core.database import Base
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

        # Create test agent and authorization in a setup session
        setup_session = SessionLocal()
        try:
            private_key, public_key = _generate_keypair()
            public_key_pem = _public_key_to_pem(public_key)

            agent = Agent(
                agent_id="AGT-RACE-001",
                name="Test Agent RACE-001",
                description="Test agent for concurrent capture/release race test",
                status=AgentStatus.ACTIVE,
                owner_type="human",
                owner_name="Test Owner",
                owner_email="test@example.com",
                owner_contact=None,
                daily_limit_usd=Decimal("0"),
                monthly_limit_usd=Decimal("0"),
            )
            setup_session.add(agent)
            setup_session.flush()
            agent_id = agent.id

            # Register credential
            credential = register_agent_credential(
                db=setup_session,
                agent=agent,
                public_key_pem=public_key_pem,
                expires_in_days=365,
            )
            credential_id = credential.id  # Store ID before session closes

            # Create spending policy
            create_spending_policy(
                db=setup_session,
                agent=agent,
                owner_id=f"human:test@example.com",
                per_transaction_limit_cents=5000,
                daily_budget_cents=10000,
                allowed_currencies=["USD"],
                allowed_merchant_ids=None,
                blocked_merchant_ids=None,
                expires_in_days=365,
            )
            setup_session.commit()
        finally:
            setup_session.close()

        # Create an ALLOW authorization decision and reservation
        # Use a fresh session for this to avoid sharing with concurrent threads
        auth_session = SessionLocal()
        try:
            auth_decision = AuthorizationDecisionRecord(
                request_id="req-race-test-001",
                idempotency_key="idem-race-test-001",
                agent_id=agent_id,
                credential_id=credential_id,
                policy_id=None,
                amount_cents=3000,
                currency="USD",
                merchant_id="MERCH-001",
                merchant_category="retail",
                description="Test concurrent capture/release transaction",
                decision=AuthorizationDecision.ALLOW,
                reasons=json.dumps(["within budget", "policy allows"]),
                policy_violations=None,
                daily_spent_before_cents=0,
                daily_spent_after_cents=3000,
                decided_at=datetime.utcnow(),
            )
            auth_session.add(auth_decision)
            auth_session.flush()
            auth_decision_id = auth_decision.id

            # Get the policy to set policy_id
            policy = get_active_policy(auth_session, agent_id)
            if policy:
                auth_decision.policy_id = policy.id

            # Create the reservation
            reservation = create_reservation(
                db=auth_session,
                auth_decision=auth_decision,
                agent_id=agent_id,
                policy_id=policy.id if policy else None,
                amount_cents=3000,
                currency="USD",
                usage_date=_get_usage_date(),
            )
            auth_session.flush()

            # Ensure DailyBudgetUsage row exists with reserved_cents = 3000
            # This mirrors what the authorization API does when creating an ALLOW decision
            usage_date = reservation.usage_date
            budget_usage = DailyBudgetUsage(
                agent_id=agent_id,
                usage_date=usage_date,
                daily_budget_cents=10000,
                reserved_cents=3000,
                captured_cents=0,
            )
            auth_session.add(budget_usage)
            auth_session.commit()

            # Verify initial reservation is RESERVED
            reservation = get_reservation_by_auth_decision(auth_session, auth_decision_id)
            assert reservation is not None
            assert reservation.status == ReservationStatus.RESERVED

            # Check initial budget - reserved_cents should be 3000
            usage = auth_session.query(DailyBudgetUsage).filter(
                DailyBudgetUsage.agent_id == agent_id
            ).first()
            assert usage is not None
            assert usage.reserved_cents == 3000
            assert usage.captured_cents == 0
            assert usage.usage_date == usage_date
        finally:
            auth_session.close()

        # Now run concurrent capture and release using separate sessions
        barrier = threading.Barrier(2)
        results = {"capture": None, "release": None, "errors": []}

        def do_capture():
            session = SessionLocal()
            try:
                barrier.wait(timeout=5)
                try:
                    success = capture_reservation(
                        db=session,
                        auth_decision_id=auth_decision_id,
                        agent_id=agent_id,
                        amount_cents=3000,
                    )
                    session.commit()
                    results["capture"] = success
                except Exception as e:
                    session.rollback()
                    results["errors"].append(("capture", e))
            finally:
                session.close()

        def do_release():
            session = SessionLocal()
            try:
                barrier.wait(timeout=5)
                try:
                    success = release_reservation(
                        db=session,
                        auth_decision_id=auth_decision_id,
                        agent_id=agent_id,
                        amount_cents=3000,
                    )
                    session.commit()
                    results["release"] = success
                except Exception as e:
                    session.rollback()
                    results["errors"].append(("release", e))
            finally:
                session.close()

        t1 = threading.Thread(target=do_capture)
        t2 = threading.Thread(target=do_release)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # Verify no unhandled exceptions
        assert len(results["errors"]) == 0, f"Unhandled exceptions: {results['errors']}"

        # Verify exactly one succeeded
        capture_success = results["capture"]
        release_success = results["release"]
        assert (capture_success and not release_success) or (release_success and not capture_success), \
            f"Exactly one should succeed: capture={capture_success}, release={release_success}"

        # Verify final state in a fresh session
        verify_session = SessionLocal()
        try:
            reservation = get_reservation_by_auth_decision(verify_session, auth_decision_id)
            usage = verify_session.query(DailyBudgetUsage).filter(
                DailyBudgetUsage.agent_id == agent_id
            ).first()

            assert reservation is not None
            assert usage is not None

            if capture_success:
                assert reservation.status == ReservationStatus.CAPTURED
                assert usage.reserved_cents == 0
                assert usage.captured_cents == 3000
            else:
                assert reservation.status == ReservationStatus.RELEASED
                assert usage.reserved_cents == 0
                assert usage.captured_cents == 0

            # No negative reserved_cents
            assert usage.reserved_cents >= 0
            assert usage.captured_cents >= 0

        finally:
            verify_session.close()

    finally:
        # Windows-safe cleanup: ensure all connections are closed before deleting file
        if engine is not None:
            engine.dispose()
        # Small delay to ensure file handles are released on Windows
        time.sleep(0.1)
        try:
            os.unlink(db_path)
        except PermissionError:
            # On Windows, sometimes the file is still locked briefly
            time.sleep(0.5)
            try:
                os.unlink(db_path)
            except PermissionError:
                pass  # Best effort cleanup