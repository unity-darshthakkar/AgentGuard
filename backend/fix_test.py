with open(r'C:\Users\5dars\Desktop\Paypal\backend\tests\test_paypal_orchestration.py', 'r') as f:
    content = f.read()

# Find and replace the function signature and the initial setup
old_sig = '''    @pytest.mark.asyncio
    async def test_atomic_failed_to_creating_retry_claim_two_sessions(self):
        """
        Test that two concurrent requests retrying a FAILED order
        results in exactly one PayPal call (atomic claim).

        This tests the conditional UPDATE in _get_or_create_attempt
        that prevents race conditions when transitioning FAILED -> CREATING.
        """
        auth_decision, reservation = allow_decision_with_reservation
        auth_decision_id = auth_decision.id

        # Create a temporary file-backed SQLite database
        import tempfile
        import os
        db_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
                db_path = tmp.name

            # Create engine and tables
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(engine)

            # Re-create the test data in this database with FAILED order
            with Session(engine) as db:
                from app.models import AuthorizationDecisionRecord, AuthorizationReservation
                new_auth = AuthorizationDecisionRecord(
                    id=auth_decision.id,
                    request_id=auth_decision.request_id,
                    idempotency_key=auth_decision.idempotency_key,
                    agent_id=auth_decision.agent_id,
                    credential_id=auth_decision.credential_id,
                    policy_id=auth_decision.policy_id,
                    amount_cents=auth_decision.amount_cents,
                    currency=auth_decision.currency,
                    merchant_id=auth_decision.merchant_id,
                    merchant_category=auth_decision.merchant_category,
                    description=auth_decision.description,
                    decision=auth_decision.decision,
                    reasons=auth_decision.reasons,
                    policy_violations=auth_decision.policy_violations,
                    daily_spent_before_cents=auth_decision.daily_spent_before_cents,
                    daily_spent_after_cents=auth_decision.daily_spent_after_cents,
                    decided_at=auth_decision.decided_at,
                )
                new_res = AuthorizationReservation(
                    id=reservation.id,
                    auth_decision_id=reservation.auth_decision_id,
                    agent_id=reservation.agent_id,
                    policy_id=reservation.policy_id,
                    amount_cents=reservation.amount_cents,
                    currency=reservation.currency,
                    usage_date=reservation.usage_date,
                    status=reservation.status,
                    reserved_at=reservation.reserved_at,
                    created_at=reservation.created_at,
                    updated_at=reservation.updated_at,
                )
                db.add(new_auth)
                db.add(new_res)
                db.commit()

                # Add a FAILED PayPal order
                failed_order = PayPalOrder(
                    auth_decision_id=auth_decision.id,
                    reservation_id=reservation.id,
                    paypal_order_id=None,
                    paypal_request_id=f"ag-{auth_decision.id}-{reservation.id}",
                    amount_cents=reservation.amount_cents,
                    currency=reservation.currency,
                    status=PayPalOrderStatus.FAILED,
                    approval_url=None,
                )
                db.add(failed_order)
                db.commit()'''

new_sig = '''    @pytest.mark.asyncio
    async def test_atomic_failed_to_creating_retry_claim_two_sessions(self, test_db: Session):
        """
        Test that two concurrent requests retrying a FAILED order
        results in exactly one PayPal call (atomic claim).

        This tests the conditional UPDATE in _get_or_create_attempt
        that prevents race conditions when transitioning FAILED -> CREATING.
        """
        # Create test data in test_db
        from app.models import Agent, AgentCredential, SpendingPolicy, AuthorizationDecisionRecord, AuthorizationReservation
        from app.models import AuthorizationDecision, CredentialStatus, PolicyStatus, ReservationStatus
        import json
        from datetime import datetime

        agent = Agent(
            agent_id="test-agent-123",
            name="Test Agent",
            description="Test agent for orchestration",
            owner_type="human",
            owner_name="Test Owner",
            owner_email="test@example.com",
            daily_limit_usd=1000.00,
            monthly_limit_usd=10000.00,
        )
        test_db.add(agent)
        test_db.commit()
        test_db.refresh(agent)

        credential = AgentCredential(
            agent_id=agent.id,
            key_id="key-test-123",
            public_key="-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA...\n-----END PUBLIC KEY-----",
            algorithm="Ed25519",
            status=CredentialStatus.ACTIVE,
        )
        test_db.add(credential)
        test_db.commit()
        test_db.refresh(credential)

        policy = SpendingPolicy(
            agent_id=agent.id,
            owner_id="human:test@example.com",
            per_transaction_limit_cents=50000,
            daily_budget_cents=100000,
            allowed_currencies=json.dumps(["USD"]),
            status=PolicyStatus.ACTIVE,
        )
        test_db.add(policy)
        test_db.commit()
        test_db.refresh(policy)

        auth_decision = AuthorizationDecisionRecord(
            request_id="req-test-123",
            idempotency_key="idem-test-123",
            agent_id=agent.id,
            credential_id=credential.id,
            policy_id=policy.id,
            amount_cents=10000,
            currency="USD",
            merchant_id="merchant-123",
            merchant_category="retail",
            description="Test purchase",
            decision=AuthorizationDecision.ALLOW,
            reasons='["Within policy limits"]',
            policy_violations=None,
            daily_spent_before_cents=0,
            daily_spent_after_cents=10000,
        )
        test_db.add(auth_decision)
        test_db.flush()

        reservation = AuthorizationReservation(
            auth_decision_id=auth_decision.id,
            agent_id=agent.id,
            policy_id=policy.id,
            amount_cents=10000,
            currency="USD",
            usage_date=datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
            status=ReservationStatus.RESERVED,
        )
        test_db.add(reservation)
        test_db.commit()
        test_db.refresh(auth_decision)
        test_db.refresh(reservation)

        # Add a FAILED PayPal order in test_db
        failed_order = PayPalOrder(
            auth_decision_id=auth_decision.id,
            reservation_id=reservation.id,
            paypal_order_id=None,
            paypal_request_id=f"ag-{auth_decision.id}-{reservation.id}",
            amount_cents=reservation.amount_cents,
            currency=reservation.currency,
            status=PayPalOrderStatus.FAILED,
            approval_url=None,
        )
        test_db.add(failed_order)
        test_db.commit()

        auth_decision_id = auth_decision.id

        # Create a temporary file-backed SQLite database for the concurrent test
        import tempfile
        import os
        db_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
                db_path = tmp.name

            # Create engine and tables
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(engine)

            # Re-create the test data in this database with FAILED order
            with Session(engine) as db:
                from app.models import AuthorizationDecisionRecord, AuthorizationReservation
                new_auth = AuthorizationDecisionRecord(
                    id=auth_decision.id,
                    request_id=auth_decision.request_id,
                    idempotency_key=auth_decision.idempotency_key,
                    agent_id=auth_decision.agent_id,
                    credential_id=auth_decision.credential_id,
                    policy_id=auth_decision.policy_id,
                    amount_cents=auth_decision.amount_cents,
                    currency=auth_decision.currency,
                    merchant_id=auth_decision.merchant_id,
                    merchant_category=auth_decision.merchant_category,
                    description=auth_decision.description,
                    decision=auth_decision.decision,
                    reasons=auth_decision.reasons,
                    policy_violations=auth_decision.policy_violations,
                    daily_spent_before_cents=auth_decision.daily_spent_before_cents,
                    daily_spent_after_cents=auth_decision.daily_spent_after_cents,
                    decided_at=auth_decision.decided_at,
                )
                new_res = AuthorizationReservation(
                    id=reservation.id,
                    auth_decision_id=reservation.auth_decision_id,
                    agent_id=reservation.agent_id,
                    policy_id=reservation.policy_id,
                    amount_cents=reservation.amount_cents,
                    currency=reservation.currency,
                    usage_date=reservation.usage_date,
                    status=reservation.status,
                    reserved_at=reservation.reserved_at,
                    created_at=reservation.created_at,
                    updated_at=reservation.updated_at,
                )
                db.add(new_auth)
                db.add(new_res)
                db.commit()

                # Add a FAILED PayPal order
                failed_order2 = PayPalOrder(
                    auth_decision_id=auth_decision.id,
                    reservation_id=reservation.id,
                    paypal_order_id=None,
                    paypal_request_id=f"ag-{auth_decision.id}-{reservation.id}",
                    amount_cents=reservation.amount_cents,
                    currency=reservation.currency,
                    status=PayPalOrderStatus.FAILED,
                    approval_url=None,
                )
                db.add(failed_order2)
                db.commit()'''

if old_sig in content:
    content = content.replace(old_sig, new_sig)
    with open(r'C:\Users\5dars\Desktop\Paypal\backend\tests\test_paypal_orchestration.py', 'w') as f:
        f.write(content)
    print("Replacement successful")
else:
    print("Old string not found")
    # Debug: find what's there
    idx = content.find('test_atomic_failed_to_creating_retry_claim_two_sessions')
    if idx >= 0:
        print("Found at:", idx)
        print("Context:", repr(content[idx:idx+200]))