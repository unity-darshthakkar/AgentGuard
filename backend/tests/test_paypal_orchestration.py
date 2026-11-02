"""Tests for PayPal Order Orchestration Service."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from sqlalchemy import select

from app.models import (
    Agent,
    AgentCredential,
    AuthorizationDecision,
    AuthorizationDecisionRecord,
    AuthorizationReservation,
    CredentialStatus,
    PolicyStatus,
    ReservationStatus,
    SpendingPolicy,
    PayPalOrder,
    PayPalOrderStatus,
    PayPalCapture,
    PayPalCaptureStatus,
)
from app.services.paypal_orchestration import (
    orchestrate_paypal_order,
    orchestrate_paypal_capture,
    get_paypal_order_binding,
    PayPalOrderBinding,
    PayPalCaptureBinding,
    PayPalOrchestrationError,
    _generate_request_id,
    _generate_capture_request_id,
)
from app.services.paypal import (
    PayPalClient,
    PayPalOrderResponse,
    PayPalCaptureResponse,
    PayPalOrderError,
    PayPalCaptureError,
    PayPalAuthenticationError,
    PayPalTimeoutError,
)
from app.core.database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import tempfile
import os


# Create an in-memory SQLite database for testing
@pytest.fixture(scope="function")
def test_db():
    """Create a fresh in-memory database for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def sample_agent(test_db: Session) -> Agent:
    """Create a sample agent."""
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
    return agent


@pytest.fixture
def sample_credential(test_db: Session, sample_agent: Agent) -> AgentCredential:
    """Create a sample credential."""
    credential = AgentCredential(
        agent_id=sample_agent.id,
        key_id="key-test-123",
        public_key="-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA...\n-----END PUBLIC KEY-----",
        algorithm="Ed25519",
        status=CredentialStatus.ACTIVE,
    )
    test_db.add(credential)
    test_db.commit()
    test_db.refresh(credential)
    return credential


@pytest.fixture
def sample_policy(test_db: Session, sample_agent: Agent) -> SpendingPolicy:
    """Create a sample spending policy."""
    import json
    policy = SpendingPolicy(
        agent_id=sample_agent.id,
        owner_id="human:test@example.com",
        per_transaction_limit_cents=50000,
        daily_budget_cents=100000,
        allowed_currencies=json.dumps(["USD"]),
        status=PolicyStatus.ACTIVE,
    )
    test_db.add(policy)
    test_db.commit()
    test_db.refresh(policy)
    return policy


@pytest.fixture
def allow_decision_with_reservation(
    test_db: Session,
    sample_agent: Agent,
    sample_credential: AgentCredential,
    sample_policy: SpendingPolicy,
) -> tuple[AuthorizationDecisionRecord, AuthorizationReservation]:
    """Create an ALLOW authorization decision with a RESERVED reservation."""
    auth_decision = AuthorizationDecisionRecord(
        request_id="req-test-123",
        idempotency_key="idem-test-123",
        agent_id=sample_agent.id,
        credential_id=sample_credential.id,
        policy_id=sample_policy.id,
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
        agent_id=sample_agent.id,
        policy_id=sample_policy.id,
        amount_cents=10000,
        currency="USD",
        usage_date=datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
        status=ReservationStatus.RESERVED,
    )
    test_db.add(reservation)
    test_db.commit()
    test_db.refresh(auth_decision)
    test_db.refresh(reservation)

    return auth_decision, reservation


@pytest.fixture
def block_decision(
    test_db: Session,
    sample_agent: Agent,
    sample_credential: AgentCredential,
    sample_policy: SpendingPolicy,
) -> AuthorizationDecisionRecord:
    """Create a BLOCK authorization decision (no reservation)."""
    auth_decision = AuthorizationDecisionRecord(
        request_id="req-block-123",
        idempotency_key="idem-block-123",
        agent_id=sample_agent.id,
        credential_id=sample_credential.id,
        policy_id=sample_policy.id,
        amount_cents=10000,
        currency="USD",
        merchant_id="merchant-123",
        merchant_category="retail",
        description="Test purchase",
        decision=AuthorizationDecision.BLOCK,
        reasons='["Over budget"]',
        policy_violations='["Daily budget exceeded"]',
        daily_spent_before_cents=90000,
        daily_spent_after_cents=90000,
    )
    test_db.add(auth_decision)
    test_db.commit()
    test_db.refresh(auth_decision)
    return auth_decision


class TestGenerateRequestId:
    """Tests for _generate_request_id helper."""

    def test_generate_request_id_format(self):
        """Test request ID format is deterministic and includes both IDs."""
        request_id = _generate_request_id(123, 456)
        assert request_id == "ag-123-456"

    def test_generate_request_id_uniqueness(self):
        """Test different inputs produce different IDs."""
        id1 = _generate_request_id(1, 2)
        id2 = _generate_request_id(1, 3)
        id3 = _generate_request_id(2, 2)
        assert id1 != id2
        assert id1 != id3
        assert id2 != id3

    def test_generate_request_id_length(self):
        """Test request ID is well within 108 character limit."""
        request_id = _generate_request_id(9999999999, 9999999999)
        assert len(request_id) <= 108


class TestOrchestratePayPalOrder:
    """Tests for orchestrate_paypal_order function."""

    @pytest.mark.asyncio
    async def test_valid_allow_reserved(self, test_db: Session, allow_decision_with_reservation):
        """Test successful orchestration with ALLOW decision and RESERVED reservation."""
        auth_decision, reservation = allow_decision_with_reservation

        # Mock PayPal client
        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock(return_value=PayPalOrderResponse(
            order_id="5O190127TN364715T",
            status="CREATED",
            approval_url="https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T",
            payer_id=None,
            create_time="2024-01-15T10:00:00Z",
            update_time="2024-01-15T10:00:00Z",
            links=[],
        ))

        result = await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        assert isinstance(result, PayPalOrderBinding)
        assert result.is_new is True
        assert result.paypal_order.paypal_order_id == "5O190127TN364715T"
        assert result.paypal_order.auth_decision_id == auth_decision.id
        assert result.paypal_order.reservation_id == reservation.id
        assert result.paypal_order.amount_cents == 10000
        assert result.paypal_order.currency == "USD"
        assert result.paypal_order.status == "created"
        assert result.paypal_order.paypal_request_id == "ag-{}-{}".format(auth_decision.id, reservation.id)

        # Verify PayPal client was called with correct parameters
        mock_client.create_order.assert_called_once_with(
            amount_cents=10000,
            currency="USD",
            request_id="ag-{}-{}".format(auth_decision.id, reservation.id),
        )

    @pytest.mark.asyncio
    async def test_block_decision_rejected(self, test_db: Session, block_decision):
        """Test BLOCK decision is rejected without PayPal call."""
        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock()

        with pytest.raises(PayPalOrchestrationError) as exc_info:
            await orchestrate_paypal_order(test_db, block_decision.id, mock_client)

        assert "block" in str(exc_info.value)
        assert "Only ALLOW decisions can be orchestrated" in str(exc_info.value)
        # Verify PayPal was NOT called
        mock_client.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_released_reservation_rejected(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test released reservation is rejected."""
        auth_decision, reservation = allow_decision_with_reservation
        # Change reservation status to RELEASED
        reservation.status = ReservationStatus.RELEASED
        test_db.commit()

        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock()

        with pytest.raises(PayPalOrchestrationError) as exc_info:
            await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        assert "released" in str(exc_info.value)
        assert "not RESERVED" in str(exc_info.value)
        mock_client.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_expired_reservation_rejected(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test expired reservation is rejected."""
        auth_decision, reservation = allow_decision_with_reservation
        # Change reservation status to EXPIRED
        reservation.status = ReservationStatus.EXPIRED
        test_db.commit()

        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock()

        with pytest.raises(PayPalOrchestrationError) as exc_info:
            await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        assert "expired" in str(exc_info.value)
        assert "not RESERVED" in str(exc_info.value)
        mock_client.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_captured_reservation_rejected(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test captured reservation is rejected."""
        auth_decision, reservation = allow_decision_with_reservation
        # Change reservation status to CAPTURED
        reservation.status = ReservationStatus.CAPTURED
        test_db.commit()

        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock()

        with pytest.raises(PayPalOrchestrationError) as exc_info:
            await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        assert "captured" in str(exc_info.value)
        assert "not RESERVED" in str(exc_info.value)
        mock_client.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_amount_mismatch_rejected(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test amount mismatch between decision and reservation is rejected."""
        auth_decision, reservation = allow_decision_with_reservation
        # Change reservation amount to not match decision
        reservation.amount_cents = 20000
        test_db.commit()

        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock()

        with pytest.raises(PayPalOrchestrationError) as exc_info:
            await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        assert "amount does not match" in str(exc_info.value)
        mock_client.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_currency_mismatch_rejected(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test currency mismatch between decision and reservation is rejected."""
        auth_decision, reservation = allow_decision_with_reservation
        # Change reservation currency to not match decision
        reservation.currency = "EUR"
        test_db.commit()

        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock()

        with pytest.raises(PayPalOrchestrationError) as exc_info:
            await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        assert "currency does not match" in str(exc_info.value)
        mock_client.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_usd_currency_rejected(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test non-USD currency is rejected."""
        auth_decision, reservation = allow_decision_with_reservation
        # Change both to EUR (decision and reservation match but not USD)
        auth_decision.currency = "EUR"
        reservation.currency = "EUR"
        test_db.commit()

        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock()

        with pytest.raises(PayPalOrchestrationError) as exc_info:
            await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        assert "requires USD" in str(exc_info.value)
        mock_client.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_repeated_request_reuses_binding(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test repeated request reuses the same PayPal order binding."""
        auth_decision, reservation = allow_decision_with_reservation

        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock(return_value=PayPalOrderResponse(
            order_id="5O190127TN364715T",
            status="CREATED",
            approval_url="https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T",
            payer_id=None,
            create_time="2024-01-15T10:00:00Z",
            update_time="2024-01-15T10:00:00Z",
            links=[],
        ))

        # First call - creates new binding
        result1 = await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)
        assert result1.is_new is True
        assert mock_client.create_order.call_count == 1

        # Second call - should reuse existing binding
        result2 = await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)
        assert result2.is_new is False
        assert result2.paypal_order.paypal_order_id == result1.paypal_order.paypal_order_id
        assert result2.paypal_order.id == result1.paypal_order.id
        # PayPal should NOT be called again
        assert mock_client.create_order.call_count == 1

    @pytest.mark.asyncio
    async def test_paypal_failure_no_binding_created(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test PayPal failure leaves no binding created (fail-closed)."""
        auth_decision, reservation = allow_decision_with_reservation

        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock(
            side_effect=PayPalOrderError("PayPal API error: Invalid request")
        )

        with pytest.raises(PayPalOrderError):
            await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        # Verify no binding was created
        binding = await get_paypal_order_binding(test_db, auth_decision.id)
        assert binding is None

    @pytest.mark.asyncio
    async def test_paypal_timeout_no_binding_created(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test PayPal timeout leaves no binding created (fail-closed)."""
        auth_decision, reservation = allow_decision_with_reservation

        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock(
            side_effect=PayPalTimeoutError("PayPal order creation timed out after 10.0s")
        )

        with pytest.raises(PayPalTimeoutError):
            await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        # Verify no binding was created
        binding = await get_paypal_order_binding(test_db, auth_decision.id)
        assert binding is None

    @pytest.mark.asyncio
    async def test_paypal_auth_error_no_binding_created(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test PayPal auth error leaves no binding created (fail-closed)."""
        auth_decision, reservation = allow_decision_with_reservation

        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock(
            side_effect=PayPalAuthenticationError("PayPal auth failed")
        )

        with pytest.raises(PayPalAuthenticationError):
            await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        # Verify no binding was created
        binding = await get_paypal_order_binding(test_db, auth_decision.id)
        assert binding is None

    @pytest.mark.asyncio
    async def test_missing_decision_rejected(self, test_db: Session):
        """Test missing authorization decision is rejected."""
        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock()

        with pytest.raises(PayPalOrchestrationError) as exc_info:
            await orchestrate_paypal_order(test_db, 99999, mock_client)

        assert "not found" in str(exc_info.value)
        mock_client.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_reservation_rejected(
        self, test_db: Session, sample_agent, sample_credential, sample_policy
    ):
        """Test missing reservation is rejected."""
        auth_decision = AuthorizationDecisionRecord(
            request_id="req-no-res-123",
            agent_id=sample_agent.id,
            credential_id=sample_credential.id,
            policy_id=sample_policy.id,
            amount_cents=10000,
            currency="USD",
            merchant_id="merchant-123",
            merchant_category="retail",
            decision=AuthorizationDecision.ALLOW,
            reasons='["Within policy limits"]',
            daily_spent_before_cents=0,
            daily_spent_after_cents=10000,
        )
        test_db.add(auth_decision)
        test_db.commit()
        test_db.refresh(auth_decision)

        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock()

        with pytest.raises(PayPalOrchestrationError) as exc_info:
            await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        assert "No reservation found" in str(exc_info.value)
        mock_client.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_reservation_wrong_decision_rejected(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test reservation not matching decision is rejected."""
        auth_decision, reservation = allow_decision_with_reservation

        # Create another decision
        other_decision = AuthorizationDecisionRecord(
            request_id="req-other-123",
            agent_id=auth_decision.agent_id,
            credential_id=auth_decision.credential_id,
            policy_id=auth_decision.policy_id,
            amount_cents=10000,
            currency="USD",
            merchant_id="merchant-123",
            merchant_category="retail",
            decision=AuthorizationDecision.ALLOW,
            reasons='["Within policy limits"]',
            daily_spent_before_cents=0,
            daily_spent_after_cents=10000,
        )
        test_db.add(other_decision)
        test_db.commit()
        test_db.refresh(other_decision)

        # Change reservation to point to other decision (but we call with original)
        reservation.auth_decision_id = other_decision.id
        test_db.commit()

        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock()

        with pytest.raises(PayPalOrchestrationError) as exc_info:
            await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        assert "No reservation found" in str(exc_info.value)
        mock_client.create_order.assert_not_called()


class TestGetPayPalOrderBinding:
    """Tests for get_paypal_order_binding function."""

    @pytest.mark.asyncio
    async def test_get_existing_binding(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test retrieving an existing PayPal order binding."""
        auth_decision, reservation = allow_decision_with_reservation

        # Create a binding directly
        paypal_order = PayPalOrder(
            auth_decision_id=auth_decision.id,
            reservation_id=reservation.id,
            paypal_order_id="EXISTING-ORDER-123",
            paypal_request_id="ag-{}-{}".format(auth_decision.id, reservation.id),
            amount_cents=10000,
            currency="USD",
            status=PayPalOrderStatus.CREATED,
            approval_url="https://example.com/approve",
        )
        test_db.add(paypal_order)
        test_db.commit()
        test_db.refresh(paypal_order)

        result = await get_paypal_order_binding(test_db, auth_decision.id)

        assert result is not None
        assert result.is_new is False
        assert result.paypal_order.paypal_order_id == "EXISTING-ORDER-123"
        assert result.paypal_response.order_id == "EXISTING-ORDER-123"

    @pytest.mark.asyncio
    async def test_get_nonexistent_binding(self, test_db: Session):
        """Test retrieving non-existent binding returns None."""
        result = await get_paypal_order_binding(test_db, 99999)
        assert result is None


class TestOrchestrationReliability:
    """Tests for payment orchestration reliability features."""

    @pytest.mark.asyncio
    async def test_creates_creating_record_before_paypal_call(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test that a CREATING record is persisted before the PayPal call."""
        auth_decision, reservation = allow_decision_with_reservation

        # Mock PayPal client that tracks if DB was committed before call
        call_order = []

        mock_client = MagicMock(spec=PayPalClient)

        async def tracked_create_order(*args, **kwargs):
            call_order.append("paypal_call")
            # Check that CREATING record exists in DB before PayPal call
            from sqlalchemy import select
            paypal_order = test_db.execute(
                select(PayPalOrder).where(PayPalOrder.auth_decision_id == auth_decision.id)
            ).scalar_one_or_none()
            assert paypal_order is not None, "CREATING record should exist before PayPal call"
            assert paypal_order.status == PayPalOrderStatus.CREATING
            assert paypal_order.paypal_order_id is None
            call_order.append("verified_creating")
            return PayPalOrderResponse(
                order_id="5O190127TN364715T",
                status="CREATED",
                approval_url="https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T",
                payer_id=None,
                create_time="2024-01-15T10:00:00Z",
                update_time="2024-01-15T10:00:00Z",
                links=[],
            )

        mock_client.create_order = tracked_create_order

        result = await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        # Verify the call order: DB commit happened before PayPal call
        assert call_order == ["paypal_call", "verified_creating"]
        assert result.is_new is True
        assert result.paypal_order.status == PayPalOrderStatus.CREATED
        assert result.paypal_order.paypal_order_id == "5O190127TN364715T"

    @pytest.mark.asyncio
    async def test_timeout_produces_unknown_state(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test that timeout produces UNKNOWN status (not FAILED, not CREATED)."""
        auth_decision, reservation = allow_decision_with_reservation

        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock(
            side_effect=PayPalTimeoutError("PayPal order creation timed out after 10.0s")
        )

        with pytest.raises(PayPalTimeoutError):
            await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        # Verify UNKNOWN record exists (not deleted, not CREATED)
        from sqlalchemy import select
        paypal_order = test_db.execute(
            select(PayPalOrder).where(PayPalOrder.auth_decision_id == auth_decision.id)
        ).scalar_one_or_none()

        assert paypal_order is not None, "Record should exist after timeout"
        assert paypal_order.status == PayPalOrderStatus.UNKNOWN
        assert paypal_order.paypal_order_id is None  # Never got order ID
        assert paypal_order.paypal_request_id == "ag-{}-{}".format(auth_decision.id, reservation.id)

        # get_paypal_order_binding should return None for UNKNOWN (only returns CREATED)
        binding = await get_paypal_order_binding(test_db, auth_decision.id)
        assert binding is None

    @pytest.mark.asyncio
    async def test_concurrent_requests_no_competing_orders(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test that concurrent requests for same authorization don't create competing orders."""
        auth_decision, reservation = allow_decision_with_reservation

        # Track PayPal calls
        paypal_call_count = 0

        mock_client = MagicMock(spec=PayPalClient)

        async def counting_create_order(*args, **kwargs):
            nonlocal paypal_call_count
            paypal_call_count += 1
            # Small delay to simulate network and allow race condition
            import asyncio
            await asyncio.sleep(0.01)
            return PayPalOrderResponse(
                order_id=f"ORDER-{paypal_call_count}",
                status="CREATED",
                approval_url=f"https://example.com/approve/{paypal_call_count}",
                payer_id=None,
                create_time="2024-01-15T10:00:00Z",
                update_time="2024-01-15T10:00:00Z",
                links=[],
            )

        mock_client.create_order = counting_create_order

        # Simulate concurrent requests by calling twice in quick succession
        import asyncio
        results = await asyncio.gather(
            orchestrate_paypal_order(test_db, auth_decision.id, mock_client),
            orchestrate_paypal_order(test_db, auth_decision.id, mock_client),
            return_exceptions=True
        )

        # One should succeed, one should fail with "already in progress" or similar
        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, Exception)]

        assert len(successes) == 1, "Exactly one request should succeed"
        assert len(failures) == 1, "One request should fail due to concurrent creation"
        assert paypal_call_count == 1, "PayPal should only be called once"

        # The successful result should have the order
        assert successes[0].is_new is True
        assert successes[0].paypal_order.paypal_order_id == "ORDER-1"

    @pytest.mark.asyncio
    async def test_same_authorization_always_same_request_id(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test that same authorization+reservation always generates same PayPal request ID."""
        auth_decision, reservation = allow_decision_with_reservation

        mock_client = MagicMock(spec=PayPalClient)
        captured_request_ids = []

        async def capture_request_id(*args, **kwargs):
            captured_request_ids.append(kwargs.get("request_id"))
            return PayPalOrderResponse(
                order_id="ORDER-123",
                status="CREATED",
                approval_url="https://example.com/approve",
                payer_id=None,
                create_time="2024-01-15T10:00:00Z",
                update_time="2024-01-15T10:00:00Z",
                links=[],
            )

        mock_client.create_order = capture_request_id

        # First call
        await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)
        # Second call (should reuse binding, not call PayPal again)
        await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        # Only one PayPal call should have happened
        assert len(captured_request_ids) == 1
        expected_id = "ag-{}-{}".format(auth_decision.id, reservation.id)
        assert captured_request_ids[0] == expected_id

    @pytest.mark.asyncio
    async def test_existing_created_binding_reused(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test that existing CREATED binding is reused without PayPal call."""
        auth_decision, reservation = allow_decision_with_reservation

        # Pre-create a CREATED binding
        paypal_order = PayPalOrder(
            auth_decision_id=auth_decision.id,
            reservation_id=reservation.id,
            paypal_order_id="PREEXISTING-ORDER-123",
            paypal_request_id="ag-{}-{}".format(auth_decision.id, reservation.id),
            amount_cents=10000,
            currency="USD",
            status=PayPalOrderStatus.CREATED,
            approval_url="https://example.com/approve/preexisting",
        )
        test_db.add(paypal_order)
        test_db.commit()

        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock()

        result = await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        # Should reuse existing binding
        assert result.is_new is False
        assert result.paypal_order.paypal_order_id == "PREEXISTING-ORDER-123"
        assert result.paypal_order.status == PayPalOrderStatus.CREATED
        # PayPal should NOT be called
        mock_client.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_status_allows_retry(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test that FAILED status allows retry with same request_id."""
        auth_decision, reservation = allow_decision_with_reservation

        mock_client = MagicMock(spec=PayPalClient)
        call_count = 0

        async def fail_then_succeed(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise PayPalOrderError("PayPal API error: Invalid request")
            return PayPalOrderResponse(
                order_id="ORDER-RETRY-123",
                status="CREATED",
                approval_url="https://example.com/approve/retry",
                payer_id=None,
                create_time="2024-01-15T10:00:00Z",
                update_time="2024-01-15T10:00:00Z",
                links=[],
            )

        mock_client.create_order = fail_then_succeed

        # First call fails
        with pytest.raises(PayPalOrderError):
            await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        # Verify FAILED status
        from sqlalchemy import select
        paypal_order = test_db.execute(
            select(PayPalOrder).where(PayPalOrder.auth_decision_id == auth_decision.id)
        ).scalar_one_or_none()
        assert paypal_order.status == PayPalOrderStatus.FAILED

        # Second call should succeed (retry)
        result = await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        assert result.is_new is True
        assert result.paypal_order.paypal_order_id == "ORDER-RETRY-123"
        assert result.paypal_order.status == PayPalOrderStatus.CREATED
        # Should have used the same request_id
        assert result.paypal_order.paypal_request_id == "ag-{}-{}".format(auth_decision.id, reservation.id)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_unknown_status_blocks_auto_retry(
        self, test_db: Session, allow_decision_with_reservation
    ):
        """Test that UNKNOWN status blocks automatic retry (requires manual reconciliation)."""
        auth_decision, reservation = allow_decision_with_reservation

        mock_client = MagicMock(spec=PayPalClient)
        mock_client.create_order = AsyncMock(
            side_effect=PayPalTimeoutError("PayPal order creation timed out")
        )

        # First call times out -> UNKNOWN
        with pytest.raises(PayPalTimeoutError):
            await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        # Verify UNKNOWN status
        from sqlalchemy import select
        paypal_order = test_db.execute(
            select(PayPalOrder).where(PayPalOrder.auth_decision_id == auth_decision.id)
        ).scalar_one_or_none()
        assert paypal_order.status == PayPalOrderStatus.UNKNOWN

        # Second call should be blocked (not auto-retry)
        with pytest.raises(PayPalOrchestrationError) as exc_info:
            await orchestrate_paypal_order(test_db, auth_decision.id, mock_client)

        assert "UNKNOWN" in str(exc_info.value)
        assert "Manual reconciliation required" in str(exc_info.value)
        # PayPal should NOT be called again
        mock_client.create_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_true_concurrent_requests_two_sessions(
        self, allow_decision_with_reservation
    ):
        """
        True concurrent request test using two independent SQLAlchemy sessions
        and a file-backed SQLite database.

        This properly models concurrent HTTP requests by:
        - Using a file-backed SQLite database (not in-memory)
        - Creating two completely independent SQLAlchemy engines/sessions
        - Running orchestration in two separate async tasks
        - Each task has its own PayPal client mock
        """
        auth_decision, reservation = allow_decision_with_reservation
        auth_decision_id = auth_decision.id

        # Create a temporary file-backed SQLite database
        import tempfile
        import os
        db_path = None
        try:
            # Create temp file first
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
                db_path = tmp.name

            # Create engine and tables
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(engine)

            # Re-create the test data in this database
            with Session(engine) as db:
                # Copy the auth_decision and reservation
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

            # Dispose the setup engine
            engine.dispose()

            # Track PayPal calls across both sessions
            paypal_calls = []
            call_lock = asyncio.Lock()

            def make_mock_client():
                mock_client = MagicMock(spec=PayPalClient)

                async def tracked_create_order(*args, **kwargs):
                    async with call_lock:
                        paypal_calls.append({
                            'request_id': kwargs.get('request_id'),
                            'amount_cents': kwargs.get('amount_cents'),
                        })
                    # Small delay to allow race condition
                    await asyncio.sleep(0.02)
                    return PayPalOrderResponse(
                        order_id=f"ORDER-{len(paypal_calls)}",
                        status="CREATED",
                        approval_url=f"https://example.com/approve/{len(paypal_calls)}",
                        payer_id=None,
                        create_time="2024-01-15T10:00:00Z",
                        update_time="2024-01-15T10:00:00Z",
                        links=[],
                    )

                mock_client.create_order = tracked_create_order
                return mock_client

            async def run_orchestration():
                """Run orchestration in a completely independent session."""
                # Create new engine and session for this "request"
                local_engine = create_engine(f"sqlite:///{db_path}")
                try:
                    with Session(local_engine) as local_db:
                        # Create a new mock client for this request
                        local_client = make_mock_client()
                        return await orchestrate_paypal_order(local_db, auth_decision_id, local_client)
                finally:
                    local_engine.dispose()

            # Run two truly concurrent requests
            results = await asyncio.gather(
                run_orchestration(),
                run_orchestration(),
                return_exceptions=True
            )

            # Analyze results
            successes = [r for r in results if not isinstance(r, Exception)]
            failures = [r for r in results if isinstance(r, Exception)]

            # Only one should succeed
            assert len(successes) == 1, f"Expected 1 success, got {len(successes)}. Failures: {failures}"
            assert len(failures) == 1, f"Expected 1 failure, got {len(failures)}"

            # Only one PayPal call should have occurred
            assert len(paypal_calls) == 1, f"Expected 1 PayPal call, got {len(paypal_calls)}: {paypal_calls}"

            # The successful result should have the order
            assert successes[0].is_new is True
            assert successes[0].paypal_order.paypal_order_id == "ORDER-1"

            # Verify the request_id is stable
            expected_request_id = f"ag-{auth_decision_id}-{reservation.id}"
            assert paypal_calls[0]['request_id'] == expected_request_id

            # Verify only one persistent order attempt exists
            verify_engine = create_engine(f"sqlite:///{db_path}")
            try:
                with Session(verify_engine) as db:
                    from sqlalchemy import select
                    orders = db.execute(
                        select(PayPalOrder).where(PayPalOrder.auth_decision_id == auth_decision_id)
                    ).scalars().all()
                    assert len(orders) == 1, f"Expected 1 order record, got {len(orders)}"
                    assert orders[0].status == PayPalOrderStatus.CREATED
                    assert orders[0].paypal_order_id == "ORDER-1"
                    assert orders[0].paypal_request_id == expected_request_id
            finally:
                verify_engine.dispose()

        finally:
            # Clean up temp file
            if db_path and os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except PermissionError:
                    pass  # On Windows, file may still be locked

    @pytest.mark.asyncio
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
                db.commit()

            # Dispose the setup engine
            engine.dispose()

            # Track PayPal calls across both sessions
            paypal_calls = []
            call_lock = asyncio.Lock()

            def make_mock_client():
                mock_client = MagicMock(spec=PayPalClient)

                async def tracked_create_order(*args, **kwargs):
                    async with call_lock:
                        paypal_calls.append({
                            'request_id': kwargs.get('request_id'),
                            'amount_cents': kwargs.get('amount_cents'),
                        })
                    # Small delay to allow race condition
                    await asyncio.sleep(0.02)
                    return PayPalOrderResponse(
                        order_id=f"ORDER-RETRY-{len(paypal_calls)}",
                        status="CREATED",
                        approval_url=f"https://example.com/approve/{len(paypal_calls)}",
                        payer_id=None,
                        create_time="2024-01-15T10:00:00Z",
                        update_time="2024-01-15T10:00:00Z",
                        links=[],
                    )

                mock_client.create_order = tracked_create_order
                return mock_client

            async def run_orchestration():
                """Run orchestration in a completely independent session."""
                local_engine = create_engine(f"sqlite:///{db_path}")
                try:
                    with Session(local_engine) as local_db:
                        local_client = make_mock_client()
                        return await orchestrate_paypal_order(local_db, auth_decision_id, local_client)
                finally:
                    local_engine.dispose()

            # Run two truly concurrent requests retrying the FAILED order
            results = await asyncio.gather(
                run_orchestration(),
                run_orchestration(),
                return_exceptions=True
            )

            # Analyze results
            successes = [r for r in results if not isinstance(r, Exception)]
            failures = [r for r in results if isinstance(r, Exception)]

            # Only one should succeed
            assert len(successes) == 1, f"Expected 1 success, got {len(successes)}. Failures: {failures}"
            assert len(failures) == 1, f"Expected 1 failure, got {len(failures)}"

            # Only one PayPal call should have occurred
            assert len(paypal_calls) == 1, f"Expected 1 PayPal call, got {len(paypal_calls)}: {paypal_calls}"

            # The successful result should have the order
            assert successes[0].is_new is True
            assert successes[0].paypal_order.paypal_order_id == "ORDER-RETRY-1"

            # Verify the request_id is stable
            expected_request_id = f"ag-{auth_decision_id}-{reservation.id}"
            assert paypal_calls[0]['request_id'] == expected_request_id

            # Verify only one persistent order attempt exists
            verify_engine = create_engine(f"sqlite:///{db_path}")
            try:
                with Session(verify_engine) as db:
                    from sqlalchemy import select
                    orders = db.execute(
                        select(PayPalOrder).where(PayPalOrder.auth_decision_id == auth_decision_id)
                    ).scalars().all()
                    assert len(orders) == 1, f"Expected 1 order record, got {len(orders)}"
                    assert orders[0].status == PayPalOrderStatus.CREATED
                    assert orders[0].paypal_order_id == "ORDER-RETRY-1"
                    assert orders[0].paypal_request_id == expected_request_id
            finally:
                verify_engine.dispose()

        finally:
            # Clean up temp file
            if db_path and os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except PermissionError:
                    pass  # On Windows, file may still be locked


class TestOrchestratePayPalCapture:
    """Tests for orchestrate_paypal_capture function."""

    @pytest.fixture
    def setup_approved_order(self, test_db: Session, sample_agent: Agent):
        """Create an approved PayPal order with RESERVED reservation."""
        from app.models import AgentCredential, SpendingPolicy, AuthorizationDecisionRecord, AuthorizationReservation, PayPalOrder, DailyBudgetUsage
        from app.models import CredentialStatus, PolicyStatus, AuthorizationDecision, ReservationStatus, PayPalOrderStatus
        import json

        credential = AgentCredential(
            agent_id=sample_agent.id,
            key_id="key-test-123",
            public_key="-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA...\n-----END PUBLIC KEY-----",
            algorithm="Ed25519",
            status=CredentialStatus.ACTIVE,
        )
        test_db.add(credential)
        test_db.commit()
        test_db.refresh(credential)

        policy = SpendingPolicy(
            agent_id=sample_agent.id,
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
            agent_id=sample_agent.id,
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

        usage_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        reservation = AuthorizationReservation(
            auth_decision_id=auth_decision.id,
            agent_id=sample_agent.id,
            policy_id=policy.id,
            amount_cents=10000,
            currency="USD",
            usage_date=usage_date,
            status=ReservationStatus.RESERVED,
        )
        test_db.add(reservation)
        test_db.flush()

        # Create DailyBudgetUsage record (as auth service would do)
        budget = DailyBudgetUsage(
            agent_id=sample_agent.id,
            usage_date=usage_date,
            daily_budget_cents=100000,
            reserved_cents=10000,
            captured_cents=0,
        )
        test_db.add(budget)
        test_db.commit()
        test_db.refresh(auth_decision)
        test_db.refresh(reservation)

        # Add a CREATED PayPal order (buyer approved)
        paypal_order = PayPalOrder(
            auth_decision_id=auth_decision.id,
            reservation_id=reservation.id,
            paypal_order_id="PAYPAL-ORDER-123",
            paypal_request_id=f"ag-{auth_decision.id}-{reservation.id}",
            amount_cents=reservation.amount_cents,
            currency=reservation.currency,
            status=PayPalOrderStatus.CREATED,
            approval_url="https://example.com/approve",
        )
        test_db.add(paypal_order)
        test_db.commit()
        test_db.refresh(paypal_order)

        return auth_decision, reservation, paypal_order

    @pytest.mark.asyncio
    async def test_successful_capture_transitions_reservation_to_captured(
        self, test_db: Session, setup_approved_order
    ):
        """Test 1: Successful approved order capture and reservation CAPTURED transition."""
        auth_decision, reservation, paypal_order = setup_approved_order

        # Mock PayPal client
        mock_client = MagicMock(spec=PayPalClient)

        # Mock GET order status (buyer approved)
        async def mock_get(*args, **kwargs):
            return {"status": "COMPLETED"}

        mock_client.get = mock_get

        # Mock capture_order
        async def mock_capture_order(*args, **kwargs):
            return PayPalCaptureResponse(
                capture_id="CAPTURE-123",
                capture_status="COMPLETED",
                order_id=paypal_order.paypal_order_id,
                order_status="COMPLETED",
                currency="USD",
                amount_cents=10000,
                create_time="2024-01-15T10:00:00Z",
                update_time="2024-01-15T10:00:00Z",
                links=[],
            )

        mock_client.capture_order = mock_capture_order

        # Execute
        result = await orchestrate_paypal_capture(test_db, auth_decision.id, mock_client)

        # Verify
        assert result.is_new is True
        assert result.paypal_capture.paypal_capture_id == "CAPTURE-123"
        assert result.paypal_capture.status == PayPalCaptureStatus.COMPLETED
        assert result.paypal_response.capture_id == "CAPTURE-123"

        # Verify reservation is CAPTURED
        test_db.refresh(reservation)
        assert reservation.status == ReservationStatus.CAPTURED

        # Verify budget was updated (reserved_cents should be 0, captured_cents should be 10000)
        from app.models import DailyBudgetUsage

        budget = test_db.execute(
            select(DailyBudgetUsage).where(
                DailyBudgetUsage.agent_id == auth_decision.agent_id,
                DailyBudgetUsage.usage_date == reservation.usage_date,
            )
        ).scalar_one()

        assert budget.reserved_cents == 0
        assert budget.captured_cents == 10000

    @pytest.mark.asyncio
    async def test_unapproved_order_rejected_without_capture_call(
        self, test_db: Session, setup_approved_order
    ):
        """Test 2: Unapproved order rejected without capture call."""
        auth_decision, reservation, paypal_order = setup_approved_order

        mock_client = MagicMock(spec=PayPalClient)

        # Mock GET order status - NOT approved
        async def mock_get(*args, **kwargs):
            return {"status": "CREATED"}  # Not COMPLETED or APPROVED

        mock_client.get = mock_get
        mock_client.capture_order = AsyncMock()

        # Execute and verify error
        with pytest.raises(PayPalOrchestrationError) as exc_info:
            await orchestrate_paypal_capture(test_db, auth_decision.id, mock_client)

        assert "not approved by buyer" in str(exc_info.value)
        assert "CREATED" in str(exc_info.value)

        # Verify capture_order was NEVER called
        mock_client.capture_order.assert_not_called()

        # Verify no capture record was created
        from app.models import PayPalCapture
        captures = test_db.execute(
            select(PayPalCapture).where(PayPalCapture.paypal_order_id == paypal_order.id)
        ).scalars().all()
        assert len(captures) == 0

    @pytest.mark.asyncio
    async def test_block_authorization_rejected(
        self, test_db: Session, sample_agent: Agent
    ):
        """Test 3: BLOCK authorization rejected."""
        from app.models import AgentCredential, SpendingPolicy, AuthorizationDecisionRecord, AuthorizationReservation, PayPalOrder
        from app.models import CredentialStatus, PolicyStatus, AuthorizationDecision, ReservationStatus, PayPalOrderStatus
        import json

        credential = AgentCredential(
            agent_id=sample_agent.id,
            key_id="key-test-123",
            public_key="-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA...\n-----END PUBLIC KEY-----",
            algorithm="Ed25519",
            status=CredentialStatus.ACTIVE,
        )
        test_db.add(credential)
        test_db.commit()
        test_db.refresh(credential)

        policy = SpendingPolicy(
            agent_id=sample_agent.id,
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
            agent_id=sample_agent.id,
            credential_id=credential.id,
            policy_id=policy.id,
            amount_cents=10000,
            currency="USD",
            merchant_id="merchant-123",
            merchant_category="retail",
            description="Test purchase",
            decision=AuthorizationDecision.BLOCK,
            reasons='["Policy violation"]',
            policy_violations='["Amount exceeds limit"]',
            daily_spent_before_cents=0,
            daily_spent_after_cents=0,
        )
        test_db.add(auth_decision)
        test_db.flush()

        reservation = AuthorizationReservation(
            auth_decision_id=auth_decision.id,
            agent_id=sample_agent.id,
            policy_id=policy.id,
            amount_cents=10000,
            currency="USD",
            usage_date=datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
            status=ReservationStatus.RESERVED,
        )
        test_db.add(reservation)
        test_db.commit()

        paypal_order = PayPalOrder(
            auth_decision_id=auth_decision.id,
            reservation_id=reservation.id,
            paypal_order_id="PAYPAL-ORDER-123",
            paypal_request_id=f"ag-{auth_decision.id}-{reservation.id}",
            amount_cents=reservation.amount_cents,
            currency=reservation.currency,
            status=PayPalOrderStatus.CREATED,
            approval_url="https://example.com/approve",
        )
        test_db.add(paypal_order)
        test_db.commit()

        mock_client = MagicMock(spec=PayPalClient)

        # Execute and verify error
        with pytest.raises(PayPalOrchestrationError) as exc_info:
            await orchestrate_paypal_capture(test_db, auth_decision.id, mock_client)

        assert "block" in str(exc_info.value).lower()
        assert "Only ALLOW decisions can be captured" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_released_reservation_rejected(
        self, test_db: Session, setup_approved_order
    ):
        """Test 4: Released/expired reservation rejected."""
        auth_decision, reservation, paypal_order = setup_approved_order

        # Change reservation to RELEASED
        reservation.status = ReservationStatus.RELEASED
        test_db.commit()

        mock_client = MagicMock(spec=PayPalClient)
        mock_client.get = AsyncMock(return_value={"status": "COMPLETED"})
        mock_client.capture_order = AsyncMock()

        # Execute and verify error
        with pytest.raises(PayPalOrchestrationError) as exc_info:
            await orchestrate_paypal_capture(test_db, auth_decision.id, mock_client)

        assert "released" in str(exc_info.value).lower()
        assert "not RESERVED" in str(exc_info.value)

        # Verify capture_order was NEVER called
        mock_client.capture_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_capture_amount_mismatch_never_marks_captured(
        self, test_db: Session, setup_approved_order
    ):
        """Test 5: Capture amount mismatch never marks CAPTURED.

        When PayPal returns COMPLETED but amount doesn't match:
        - Never mark reservation CAPTURED
        - Mark capture as UNKNOWN (reconciliation required) since PayPal may have captured funds
        - Preserve the actual PayPal capture ID and observed amount
        - Raise PayPalOrchestrationError
        """
        auth_decision, reservation, paypal_order = setup_approved_order

        mock_client = MagicMock(spec=PayPalClient)

        # Mock GET order status
        async def mock_get(*args, **kwargs):
            return {"status": "COMPLETED"}

        mock_client.get = mock_get

        # Mock capture_order returning WRONG amount (simulating PayPal bug/attack)
        async def mock_capture_order(*args, **kwargs):
            return PayPalCaptureResponse(
                capture_id="CAPTURE-123",
                capture_status="COMPLETED",
                order_id=paypal_order.paypal_order_id,
                order_status="COMPLETED",
                currency="USD",
                amount_cents=5000,  # WRONG amount - different from reservation (10000)
                create_time="2024-01-15T10:00:00Z",
                update_time="2024-01-15T10:00:00Z",
                links=[],
            )

        mock_client.capture_order = mock_capture_order

        # Execute and verify error
        with pytest.raises(PayPalOrchestrationError) as exc_info:
            await orchestrate_paypal_capture(test_db, auth_decision.id, mock_client)

        assert "does not match reservation" in str(exc_info.value)
        assert "5000" in str(exc_info.value)
        assert "10000" in str(exc_info.value)
        assert "reconciliation" in str(exc_info.value).lower()

        # Verify reservation is STILL RESERVED (not CAPTURED)
        test_db.refresh(reservation)
        assert reservation.status == ReservationStatus.RESERVED

        # Verify capture record is UNKNOWN (not FAILED) - reconciliation required
        from app.models import PayPalCapture
        capture = test_db.execute(
            select(PayPalCapture).where(PayPalCapture.paypal_order_id == paypal_order.id)
        ).scalar_one()
        assert capture.status == PayPalCaptureStatus.UNKNOWN
        # Verify the PayPal capture ID is preserved for audit
        assert capture.paypal_capture_id == "CAPTURE-123"
        assert capture.amount_cents == 10000  # Our expected amount (not the wrong one)

    @pytest.mark.asyncio
    async def test_timeout_produces_unknown_without_auto_retry(
        self, test_db: Session, setup_approved_order
    ):
        """Test 6: Timeout produces UNKNOWN without automatic retry."""
        auth_decision, reservation, paypal_order = setup_approved_order

        mock_client = MagicMock(spec=PayPalClient)

        async def mock_get(*args, **kwargs):
            return {"status": "COMPLETED"}

        mock_client.get = mock_get

        # Mock capture_order to raise timeout
        async def mock_capture_order(*args, **kwargs):
            raise PayPalTimeoutError("Request timed out")

        mock_client.capture_order = mock_capture_order

        # Execute and verify timeout error
        with pytest.raises(PayPalTimeoutError):
            await orchestrate_paypal_capture(test_db, auth_decision.id, mock_client)

        # Verify capture record is UNKNOWN
        from app.models import PayPalCapture
        capture = test_db.execute(
            select(PayPalCapture).where(PayPalCapture.paypal_order_id == paypal_order.id)
        ).scalar_one()
        assert capture.status == PayPalCaptureStatus.UNKNOWN
        assert capture.paypal_capture_id is None

        # Verify reservation is STILL RESERVED
        test_db.refresh(reservation)
        assert reservation.status == ReservationStatus.RESERVED

        # Second attempt with same request should fail with UNKNOWN status error
        mock_client.capture_order = AsyncMock(return_value=PayPalCaptureResponse(
            capture_id="CAPTURE-456",
            capture_status="COMPLETED",
            order_id=paypal_order.paypal_order_id,
            order_status="COMPLETED",
            currency="USD",
            amount_cents=10000,
            create_time="2024-01-15T10:00:00Z",
            update_time="2024-01-15T10:00:00Z",
            links=[],
        ))

        with pytest.raises(PayPalOrchestrationError) as exc_info:
            await orchestrate_paypal_capture(test_db, auth_decision.id, mock_client)

        assert "timed out" in str(exc_info.value)
        assert "UNKNOWN" in str(exc_info.value)
        assert "Manual reconciliation required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_repeated_completed_capture_does_not_call_paypal_again(
        self, test_db: Session, setup_approved_order
    ):
        """Test 7: Repeated completed capture does not call PayPal again.

        When capture is already COMPLETED and reservation is CAPTURED:
        - Return existing capture without calling PayPal
        - Do not double-count budget usage
        """
        auth_decision, reservation, paypal_order = setup_approved_order

        mock_client = MagicMock(spec=PayPalClient)

        async def mock_get(*args, **kwargs):
            return {"status": "COMPLETED"}

        mock_client.get = mock_get

        async def mock_capture_order(*args, **kwargs):
            return PayPalCaptureResponse(
                capture_id="CAPTURE-123",
                capture_status="COMPLETED",
                order_id=paypal_order.paypal_order_id,
                order_status="COMPLETED",
                currency="USD",
                amount_cents=10000,
                create_time="2024-01-15T10:00:00Z",
                update_time="2024-01-15T10:00:00Z",
                links=[],
            )

        mock_client.capture_order = mock_capture_order

        # First capture
        result1 = await orchestrate_paypal_capture(test_db, auth_decision.id, mock_client)
        assert result1.is_new is True
        assert result1.paypal_capture.paypal_capture_id == "CAPTURE-123"

        # Verify reservation is now CAPTURED
        test_db.refresh(reservation)
        assert reservation.status == ReservationStatus.CAPTURED

        # Verify budget was updated (reserved_cents=0, captured_cents=10000)
        from app.models import DailyBudgetUsage
        from sqlalchemy import select
        budget = test_db.execute(
            select(DailyBudgetUsage).where(
                DailyBudgetUsage.agent_id == auth_decision.agent_id,
                DailyBudgetUsage.usage_date == reservation.usage_date,
            )
        ).scalar_one()
        assert budget.reserved_cents == 0
        assert budget.captured_cents == 10000

        # Reset mock to detect second call
        call_count = [0]
        original_capture = mock_client.capture_order

        async def counting_capture(*args, **kwargs):
            call_count[0] += 1
            return await original_capture(*args, **kwargs)

        mock_client.capture_order = counting_capture

        # Second capture (should reuse existing without calling PayPal)
        result2 = await orchestrate_paypal_capture(test_db, auth_decision.id, mock_client)
        assert result2.is_new is False
        assert result2.paypal_capture.paypal_capture_id == "CAPTURE-123"

        # Verify PayPal was only called ONCE
        assert call_count[0] == 0, f"Expected 0 additional PayPal calls, got {call_count[0]}"

        # Verify budget was NOT double-counted
        test_db.refresh(reservation)
        assert reservation.status == ReservationStatus.CAPTURED
        budget = test_db.execute(
            select(DailyBudgetUsage).where(
                DailyBudgetUsage.agent_id == auth_decision.agent_id,
                DailyBudgetUsage.usage_date == reservation.usage_date,
            )
        ).scalar_one()
        assert budget.reserved_cents == 0
        assert budget.captured_cents == 10000

    @pytest.mark.asyncio
    async def test_concurrent_capture_attempts_cannot_both_call_paypal(
        self, test_db: Session, sample_agent: Agent
    ):
        """Test 8: Concurrent capture attempts cannot both call PayPal."""
        from app.models import AgentCredential, SpendingPolicy, AuthorizationDecisionRecord, AuthorizationReservation, PayPalOrder, PayPalCapture, DailyBudgetUsage
        from app.models import CredentialStatus, PolicyStatus, AuthorizationDecision, ReservationStatus, PayPalOrderStatus, PayPalCaptureStatus
        import json
        import tempfile
        import os
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session as SessionClass

        # Create test data in main DB first
        credential = AgentCredential(
            agent_id=sample_agent.id,
            key_id="key-test-123",
            public_key="-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA...\n-----END PUBLIC KEY-----",
            algorithm="Ed25519",
            status=CredentialStatus.ACTIVE,
        )
        test_db.add(credential)
        test_db.commit()
        test_db.refresh(credential)

        policy = SpendingPolicy(
            agent_id=sample_agent.id,
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
            agent_id=sample_agent.id,
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
            agent_id=sample_agent.id,
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

        # Add a CREATED PayPal order
        paypal_order = PayPalOrder(
            auth_decision_id=auth_decision.id,
            reservation_id=reservation.id,
            paypal_order_id="PAYPAL-ORDER-123",
            paypal_request_id=f"ag-{auth_decision.id}-{reservation.id}",
            amount_cents=reservation.amount_cents,
            currency=reservation.currency,
            status=PayPalOrderStatus.CREATED,
            approval_url="https://example.com/approve",
        )
        test_db.add(paypal_order)
        test_db.commit()
        test_db.refresh(paypal_order)

        auth_decision_id = auth_decision.id
        paypal_order_id = paypal_order.id

        # Create a temporary file-backed SQLite database for the concurrent test
        db_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
                db_path = tmp.name

            # Create engine and tables
            engine = create_engine(f"sqlite:///{db_path}")
            from app.core.database import Base
            Base.metadata.create_all(engine)

            # Re-create the test data in this database
            with SessionClass(engine) as db:
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

                # Add DailyBudgetUsage record (required for capture_reservation)
                new_budget = DailyBudgetUsage(
                    agent_id=sample_agent.id,
                    usage_date=reservation.usage_date,
                    daily_budget_cents=100000,
                    reserved_cents=reservation.amount_cents,
                    captured_cents=0,
                )
                db.add(new_budget)
                db.commit()

                # Add a CREATED PayPal order
                new_order = PayPalOrder(
                    id=paypal_order.id,
                    auth_decision_id=paypal_order.auth_decision_id,
                    reservation_id=paypal_order.reservation_id,
                    paypal_order_id=paypal_order.paypal_order_id,
                    paypal_request_id=paypal_order.paypal_request_id,
                    amount_cents=paypal_order.amount_cents,
                    currency=paypal_order.currency,
                    status=paypal_order.status,
                    approval_url=paypal_order.approval_url,
                    created_at=paypal_order.created_at,
                    updated_at=paypal_order.updated_at,
                )
                db.add(new_order)
                db.commit()

            engine.dispose()

            # Track PayPal calls across both sessions
            paypal_calls = []
            call_lock = asyncio.Lock()

            def make_mock_client():
                mock_client = MagicMock(spec=PayPalClient)

                async def mock_get(*args, **kwargs):
                    return {"status": "COMPLETED"}

                mock_client.get = mock_get

                async def tracked_capture_order(*args, **kwargs):
                    async with call_lock:
                        paypal_calls.append({
                            'request_id': kwargs.get('request_id'),
                            'amount_cents': kwargs.get('amount_cents'),
                        })
                    # Small delay to allow race condition
                    await asyncio.sleep(0.02)
                    return PayPalCaptureResponse(
                        capture_id=f"CAPTURE-{len(paypal_calls)}",
                        capture_status="COMPLETED",
                        order_id=paypal_order_id,
                        order_status="COMPLETED",
                        currency="USD",
                        amount_cents=10000,
                        create_time="2024-01-15T10:00:00Z",
                        update_time="2024-01-15T10:00:00Z",
                        links=[],
                    )

                mock_client.capture_order = tracked_capture_order
                return mock_client

            async def run_capture():
                """Run capture in a completely independent session."""
                local_engine = create_engine(f"sqlite:///{db_path}")
                try:
                    with SessionClass(local_engine) as local_db:
                        local_client = make_mock_client()
                        return await orchestrate_paypal_capture(local_db, auth_decision_id, local_client)
                finally:
                    local_engine.dispose()

            # Run two truly concurrent requests capturing the same order
            results = await asyncio.gather(
                run_capture(),
                run_capture(),
                return_exceptions=True
            )

            # Analyze results
            successes = [r for r in results if not isinstance(r, Exception)]
            failures = [r for r in results if isinstance(r, Exception)]

            # Only one should succeed
            assert len(successes) == 1, f"Expected 1 success, got {len(successes)}. Failures: {failures}"
            assert len(failures) == 1, f"Expected 1 failure, got {len(failures)}"

            # Only one PayPal call should have occurred
            assert len(paypal_calls) == 1, f"Expected 1 PayPal call, got {len(paypal_calls)}: {paypal_calls}"

            # The successful result should have the capture
            assert successes[0].is_new is True
            assert successes[0].paypal_capture.paypal_capture_id == "CAPTURE-1"

            # Verify the request_id is stable
            expected_capture_request_id = f"ag-cap-{auth_decision_id}-{reservation.id}"
            assert paypal_calls[0]['request_id'] == expected_capture_request_id

            # Verify only one persistent capture attempt exists
            verify_engine = create_engine(f"sqlite:///{db_path}")
            try:
                with SessionClass(verify_engine) as db:
                    from sqlalchemy import select
                    captures = db.execute(
                        select(PayPalCapture).where(PayPalCapture.paypal_order_id == paypal_order_id)
                    ).scalars().all()
                    assert len(captures) == 1, f"Expected 1 capture record, got {len(captures)}"
                    assert captures[0].status == PayPalCaptureStatus.COMPLETED
                    assert captures[0].paypal_capture_id == "CAPTURE-1"
                    assert captures[0].paypal_request_id == expected_capture_request_id
            finally:
                verify_engine.dispose()

        finally:
            # Clean up temp file
            if db_path and os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except PermissionError:
                    pass  # On Windows, file may still be locked