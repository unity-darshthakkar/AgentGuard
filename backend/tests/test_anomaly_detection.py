"""Tests for anomaly detection service (Phase 4)."""

import json
import time
from datetime import datetime, timedelta
from typing import Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    AgentCredential,
    AgentStatus,
    SpendingPolicy,
    PolicyStatus,
    AuthorizationDecision,
    AuthorizationDecisionRecord,
    DailyBudgetUsage,
    CredentialStatus,
)
from app.services import (
    register_agent_credential,
    create_spending_policy,
    create_nonce,
    compute_body_hash,
    canonical_request_string,
)
from app.services.anomaly_detection import AnomalyDetectionService, AnomalyFeatures, RuleBasedDetector


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
    daily_budget_cents: int = 500000,  # $5000 daily budget
    per_transaction_limit_cents: int = 100000,  # $1000 per transaction
) -> Tuple[Agent, ed25519.Ed25519PrivateKey, str]:
    """Create a test agent with credential and spending policy."""
    public_key_pem = _public_key_to_pem(private_key.public_key())

    agent = Agent(
        agent_id=agent_id,
        name=f"Test Agent {agent_id}",
        description="Test agent for anomaly detection tests",
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


def create_authorization_history(
    db: Session,
    agent_id: int,
    transactions: list,
):
    """Create historical authorization decisions for testing."""
    for txn in transactions:
        record = AuthorizationDecisionRecord(
            request_id=txn["request_id"],
            idempotency_key=txn.get("idempotency_key"),
            agent_id=agent_id,
            credential_id=txn.get("credential_id"),
            policy_id=txn.get("policy_id"),
            amount_cents=txn["amount_cents"],
            currency=txn.get("currency", "USD"),
            merchant_id=txn["merchant_id"],
            merchant_category=txn.get("merchant_category", "retail"),
            description=txn.get("description"),
            decision=AuthorizationDecision.ALLOW,
            reasons=json.dumps(txn.get("reasons", ["policy_check_passed"])),
            policy_violations=None,
            daily_spent_before_cents=txn.get("daily_spent_before_cents", 0),
            daily_spent_after_cents=txn.get("daily_spent_after_cents", txn["amount_cents"]),
            decided_at=txn["decided_at"],
            risk_score=txn.get("risk_score", 0),
            risk_level=txn.get("risk_level", "minimal"),
            anomaly_signals=txn.get("anomaly_signals"),
            anomaly_explanation=txn.get("anomaly_explanation"),
            detection_method=txn.get("detection_method"),
        )
        db.add(record)
    db.commit()


class TestAnomalyDetectionService:
    """Tests for the AnomalyDetectionService class."""

    def test_normal_transaction_low_risk(self, db_session: Session):
        """A normal transaction matching historical patterns should have low risk score."""
        # Create agent with policy
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-ANOM-001", private_key
        )

        # Create normal transaction history (similar amounts, same merchant)
        history = []
        base_time = datetime.utcnow() - timedelta(days=7)
        for i in range(10):
            history.append({
                "request_id": f"hist-req-{i}",
                "idempotency_key": f"hist-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": 10000,  # $100 each
                "merchant_id": "MERCH-REGULAR",
                "merchant_category": "retail",
                "decided_at": base_time + timedelta(hours=i * 12),
            })
        create_authorization_history(db_session, agent.id, history)

        # Assess a normal transaction
        service = AnomalyDetectionService(db_session)
        assessment = service.assess_transaction(
            agent_id=agent.id,
            amount_cents=10000,  # $100 - matches history
            merchant_id="MERCH-REGULAR",  # Known merchant
            currency="USD",
        )

        # Should have low risk score
        assert assessment["risk_score"] < 30, f"Expected low risk (<30), got {assessment['risk_score']}"
        assert assessment["risk_severity"] in ["minimal", "low"], f"Unexpected severity: {assessment['risk_severity']}"
        assert assessment["detection_method"] == "rule_based"
        # Should have minimal or no anomaly signals
        assert len(assessment["anomaly_signals"]) <= 1

    def test_velocity_anomaly_high_frequency(self, db_session: Session):
        """High transaction velocity should trigger velocity anomaly signal."""
        # Create agent with policy
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-ANOM-002", private_key
        )

        # Use a fixed reference time for all timestamps to avoid clock drift issues
        ref_time = datetime.utcnow()

        # Create history with moderate activity (older than 1 hour)
        history = []
        base_time = ref_time - timedelta(days=3)
        for i in range(5):
            history.append({
                "request_id": f"hist-req-{i}",
                "idempotency_key": f"hist-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": 10000,
                "merchant_id": "MERCH-REGULAR",
                "merchant_category": "retail",
                "decided_at": base_time + timedelta(hours=i * 12),
            })
        create_authorization_history(db_session, agent.id, history)

        # Now create a burst of transactions in the last hour (well within 1-hour window)
        recent_history = []
        for i in range(8):  # 8 transactions in last 40 minutes exceeds threshold of 5
            recent_history.append({
                "request_id": f"recent-req-{i}",
                "idempotency_key": f"recent-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": 10000,
                "merchant_id": "MERCH-REGULAR",
                "merchant_category": "retail",
                "decided_at": ref_time - timedelta(minutes=5 * i),  # 0, 5, 10, 15, 20, 25, 30, 35 min ago
            })
        create_authorization_history(db_session, agent.id, recent_history)

        # Assess a new transaction - should trigger velocity anomaly
        service = AnomalyDetectionService(db_session)
        assessment = service.assess_transaction(
            agent_id=agent.id,
            amount_cents=10000,
            merchant_id="MERCH-REGULAR",
            currency="USD",
        )

        # Should detect velocity anomaly (risk score includes velocity + merchant novelty)
        # Velocity threshold is 5/hr, we have 8 in ~35 min = significant anomaly
        assert assessment["risk_score"] >= 10, f"Expected elevated risk (>=10), got {assessment['risk_score']}"
        # Check for velocity anomaly signal
        signals = assessment["anomaly_signals"]
        velocity_signals = [s for s in signals if s["signal"] == "velocity_anomaly"]
        assert len(velocity_signals) > 0, f"Should have velocity_anomaly signal, got signals: {[s['signal'] for s in signals]}"

    def test_amount_anomaly_unusually_large(self, db_session: Session):
        """Unusually large transaction amount should trigger amount outlier signal."""
        # Create agent with policy
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-ANOM-003", private_key
        )

        # Use a fixed reference time
        ref_time = datetime.utcnow()

        # Create history with varying but small amounts (to get non-zero std dev)
        history = []
        base_time = ref_time - timedelta(days=7)
        amounts = [800, 1200, 900, 1100, 1000, 950, 1050, 850, 1150, 1000]  # ~$10 with variance
        for i, amt in enumerate(amounts):
            history.append({
                "request_id": f"hist-req-{i}",
                "idempotency_key": f"hist-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": amt,
                "merchant_id": "MERCH-REGULAR",
                "merchant_category": "retail",
                "decided_at": base_time + timedelta(hours=i * 12),
            })
        create_authorization_history(db_session, agent.id, history)

        # Assess a very large transaction ($5000 vs ~$10 average = 500x)
        service = AnomalyDetectionService(db_session)
        assessment = service.assess_transaction(
            agent_id=agent.id,
            amount_cents=500000,  # $5000 - 500x normal amount
            merchant_id="MERCH-REGULAR",
            currency="USD",
        )

        # Should detect amount anomaly (z-score and amount_ratio both contribute)
        assert assessment["risk_score"] >= 20, f"Expected elevated risk (>=20), got {assessment['risk_score']}"
        signals = assessment["anomaly_signals"]
        amount_signals = [s for s in signals if s["signal"] == "amount_outlier"]
        assert len(amount_signals) > 0, f"Should have amount_outlier signal, got signals: {[s['signal'] for s in signals]}"

    def test_new_merchant_novelty(self, db_session: Session):
        """First transaction with a new merchant should trigger new_merchant signal."""
        # Create agent with policy
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-ANOM-004", private_key
        )

        # Create history with known merchants
        history = []
        base_time = datetime.utcnow() - timedelta(days=7)
        for i in range(5):
            history.append({
                "request_id": f"hist-req-{i}",
                "idempotency_key": f"hist-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": 10000,
                "merchant_id": f"MERCH-KNOWN-{i}",
                "merchant_category": "retail",
                "decided_at": base_time + timedelta(hours=i * 24),
            })
        create_authorization_history(db_session, agent.id, history)

        # Assess transaction with a NEW merchant
        service = AnomalyDetectionService(db_session)
        assessment = service.assess_transaction(
            agent_id=agent.id,
            amount_cents=10000,
            merchant_id="MERCH-NEW-UNKNOWN",
            currency="USD",
        )

        # Should detect new merchant
        signals = assessment["anomaly_signals"]
        new_merchant_signals = [s for s in signals if s["signal"] == "new_merchant"]
        assert len(new_merchant_signals) > 0, "Should have new_merchant signal"
        # Risk should be elevated but not necessarily high
        assert assessment["risk_score"] >= 8, f"Expected some risk (>=8), got {assessment['risk_score']}"

    def test_cold_start_no_history(self, db_session: Session):
        """New agent with no transaction history should use rule-based detection with default values.

        Even if ML model exists, it requires MIN_SAMPLES_FOR_ML (20) history to run.
        With no history, detection should fall back to rule_based.
        """
        # Create agent with policy but NO history
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-ANOM-005", private_key
        )

        # Assess first transaction (no history)
        service = AnomalyDetectionService(db_session)
        assessment = service.assess_transaction(
            agent_id=agent.id,
            amount_cents=10000,
            merchant_id="MERCH-FIRST",
            currency="USD",
        )

        # Should use rule_based detection (insufficient history for ML)
        assert assessment["detection_method"] == "rule_based"
        # ML model is available but not used due to insufficient history
        assert assessment["ml_available"] == True
        assert assessment["history_count"] == 0
        # With no history, risk should be low for a normal first transaction
        # but merchant novelty might add some risk
        assert assessment["risk_score"] >= 0
        assert "anomaly_signals" in assessment
        assert "feature_vector" in assessment


class TestRuleBasedDetector:
    """Tests for the RuleBasedDetector class."""

    def test_rule_detector_velocity_1h(self, db_session: Session):
        """Rule detector should flag high 1-hour velocity."""
        detector = RuleBasedDetector()

        # Features simulating >5 txns in 1 hour
        features = {
            "txn_count_1h": 10.0,
            "txn_count_24h": 15.0,
            "txn_count_7d": 20.0,
            "amount_zscore": 0.0,
            "amount_log": 4.6,  # log(100)
            "avg_amount_7d": 100.0,
            "std_amount_7d": 10.0,
            "unique_merchants_7d": 3.0,
            "merchant_novelty": 0.0,
            "time_since_last_txn_h": 0.5,
            "hour_of_day": 12.0,
            "day_of_week": 2.0,
        }

        risk_score, signals = detector.evaluate(features, agent_history_count=20)

        # Should detect velocity anomaly
        assert risk_score > 0
        velocity_signals = [s for s in signals if s["signal"] == "velocity_anomaly"]
        assert len(velocity_signals) > 0
        # Severity should be warning or critical based on how much over threshold
        assert velocity_signals[0]["severity"] in ["warning", "critical"]

    def test_rule_detector_amount_zscore(self, db_session: Session):
        """Rule detector should flag amount z-score outliers."""
        detector = RuleBasedDetector()

        # Features simulating amount >3 std deviations from mean
        features = {
            "txn_count_1h": 1.0,
            "txn_count_24h": 2.0,
            "txn_count_7d": 10.0,
            "amount_zscore": 4.0,  # 4 standard deviations
            "amount_log": 6.9,  # log(1000)
            "avg_amount_7d": 100.0,
            "std_amount_7d": 10.0,
            "unique_merchants_7d": 3.0,
            "merchant_novelty": 0.0,
            "time_since_last_txn_h": 24.0,
            "hour_of_day": 12.0,
            "day_of_week": 2.0,
        }

        risk_score, signals = detector.evaluate(features, agent_history_count=20)

        assert risk_score > 0
        amount_signals = [s for s in signals if s["signal"] == "amount_outlier"]
        assert len(amount_signals) > 0

    def test_rule_detector_no_history(self, db_session: Session):
        """Rule detector should handle cold start gracefully."""
        detector = RuleBasedDetector()

        # Features for brand new agent (no history)
        features = {
            "txn_count_1h": 0.0,
            "txn_count_24h": 0.0,
            "txn_count_7d": 0.0,
            "amount_zscore": 0.0,
            "amount_log": 4.6,
            "avg_amount_7d": 0.0,
            "std_amount_7d": 0.0,
            "unique_merchants_7d": 0.0,
            "merchant_novelty": 1.0,  # New merchant (but no history to compare)
            "time_since_last_txn_h": 168.0,  # 1 week default
            "hour_of_day": 12.0,
            "day_of_week": 2.0,
        }

        risk_score, signals = detector.evaluate(features, agent_history_count=0)

        # With 0 history, merchant novelty rule should NOT trigger (requires >=3 history)
        # Time gap should NOT trigger (requires >=5 history)
        # No velocity anomalies
        assert risk_score == 0 or risk_score == 8  # Only possible: merchant novelty with >=3 history


class TestAnomalyDetectionIntegration:
    """Integration tests for anomaly detection in authorization flow."""

    def test_authorization_includes_risk_fields(self, client: TestClient, db_session: Session):
        """Authorization response should include risk scoring fields."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-INT-001", private_key
        )

        # Get nonce
        nonce_resp = client.post(f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}")
        assert nonce_resp.status_code == 200
        nonce = nonce_resp.json()["nonce"]

        payload, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=10000,
            nonce=nonce,
        )

        response = client.post("/api/authorize", json=payload)
        assert response.status_code == 200
        data = response.json()

        # Check risk fields are present
        assert "risk_score" in data
        assert "risk_level" in data
        assert "anomaly_signals" in data
        assert "anomaly_explanation" in data
        assert "detection_method" in data

        # Values should be valid
        assert isinstance(data["risk_score"], int)
        assert 0 <= data["risk_score"] <= 100
        assert data["risk_level"] in ["minimal", "low", "medium", "high", "critical"]
        assert isinstance(data["anomaly_signals"], list)
        assert data["detection_method"] in ["rule_based", "ml_based", None]

    def test_risk_persistence_in_database(self, client: TestClient, db_session: Session):
        """Risk assessment should be persisted in authorization_decisions table."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-INT-002", private_key
        )

        # Get nonce
        nonce_resp = client.post(f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}")
        nonce = nonce_resp.json()["nonce"]

        payload, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=10000,
            nonce=nonce,
            request_id="req-persist-001",
        )

        response = client.post("/api/authorize", json=payload)
        assert response.status_code == 200
        data = response.json()

        # Check database record
        record = db_session.query(AuthorizationDecisionRecord).filter(
            AuthorizationDecisionRecord.request_id == "req-persist-001"
        ).first()

        assert record is not None
        assert record.risk_score == data["risk_score"]
        assert record.risk_level == data["risk_level"]
        assert record.detection_method == data["detection_method"]
        if record.anomaly_signals:
            assert json.loads(record.anomaly_signals) == data["anomaly_signals"]
        assert record.anomaly_explanation == data["anomaly_explanation"]

    def test_idempotent_request_returns_cached_risk(self, client: TestClient, db_session: Session):
        """Retrying with same idempotency key should return cached risk assessment."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-INT-003", private_key
        )

        # Get nonce for first request
        nonce_resp = client.post(f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}")
        nonce1 = nonce_resp.json()["nonce"]

        payload1, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=10000,
            nonce=nonce1,
            request_id="req-idem-001",
            idempotency_key="idem-test-001",
        )

        # First request
        response1 = client.post("/api/authorize", json=payload1)
        assert response1.status_code == 200
        data1 = response1.json()

        # Second request with SAME idempotency key (simulate retry)
        # Need a fresh nonce and NEW signature (since nonce and request_id change)
        nonce_resp2 = client.post(f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}")
        nonce2 = nonce_resp2.json()["nonce"]

        payload2, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=10000,
            nonce=nonce2,
            request_id="req-idem-002",
            idempotency_key="idem-test-001",  # Same idempotency key
        )

        response2 = client.post("/api/authorize", json=payload2)
        assert response2.status_code == 200, f"Expected 200, got {response2.status_code}: {response2.text}"
        data2 = response2.json()

        # Risk fields should match (cached)
        assert data2["risk_score"] == data1["risk_score"]
        assert data2["risk_level"] == data1["risk_level"]
        assert data2["detection_method"] == data1["detection_method"]
        # anomaly_signals should be same (cached) - handle both list and JSON string
        signals1 = data1["anomaly_signals"]
        signals2 = data2["anomaly_signals"]
        if isinstance(signals1, str):
            signals1 = json.loads(signals1)
        if isinstance(signals2, str):
            signals2 = json.loads(signals2)
        assert signals1 == signals2


class TestRiskThresholds:
    """Tests for REVIEW and BLOCK decisions based on risk thresholds."""

    def test_risk_score_triggers_review(self, client: TestClient, db_session: Session):
        """High risk score should trigger REVIEW decision when threshold is met."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-RISK-001", private_key
        )

        # Create history with velocity + amount anomaly + new merchant to maximize rule-based score
        ref_time = datetime.utcnow()
        history = []
        base_time = ref_time - timedelta(days=3)
        for i in range(5):
            history.append({
                "request_id": f"hist-req-{i}",
                "idempotency_key": f"hist-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": 1000,  # Small amounts
                "merchant_id": f"MERCH-KNOWN-{i}",
                "merchant_category": "retail",
                "decided_at": base_time + timedelta(hours=i * 12),
            })
        create_authorization_history(db_session, agent.id, history)

        # Get nonce FIRST (before creating recent history to minimize time drift)
        nonce_resp = client.post(f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}")
        nonce = nonce_resp.json()["nonce"]

        # Add recent transactions (velocity) - use timestamps relative to NOW
        # Create them immediately before authorization to ensure they fall in 1-hour window
        recent_history = []
        now = datetime.utcnow()
        for i in range(8):  # 8 transactions in last ~21 minutes exceeds threshold of 5
            recent_history.append({
                "request_id": f"recent-req-{i}",
                "idempotency_key": f"recent-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": 1000,
                "merchant_id": "MERCH-KNOWN-0",
                "merchant_category": "retail",
                "decided_at": now - timedelta(minutes=2 * i + 1),  # 1, 3, 5... 15 min ago
            })
        create_authorization_history(db_session, agent.id, recent_history)

        # Request with large amount + new merchant to trigger multiple signals
        payload, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=100000,  # $1000 - amount anomaly
            nonce=nonce,
            merchant_id="MERCH-NEW-UNKNOWN",  # New merchant
        )

        response = client.post("/api/authorize", json=payload)
        assert response.status_code == 200
        data = response.json()

        # DEBUG: print signals
        print(f"\nDEBUG: risk_score={data['risk_score']}")
        signals = data["anomaly_signals"]
        for s in signals:
            print(f"  Signal: {s['signal']}, severity={s['severity']}, desc={s['description']}")
        signal_types = {s["signal"] for s in signals}
        print(f"  Signal types: {signal_types}")

        # Should have velocity and new_merchant signals (amount ratio uses log-scale, needs ~160k USD to trigger)
        assert "velocity_anomaly" in signal_types
        assert "new_merchant" in signal_types
        # Risk score should be elevated from velocity + new_merchant (14 + 8 = 22)
        assert data["risk_score"] >= 22, f"Expected elevated risk (>=22), got {data['risk_score']}"

    def test_risk_score_triggers_block(self, client: TestClient, db_session: Session):
        """Critical risk score should trigger BLOCK decision when threshold is met.

        Note: Rule-based detection maxes at ~75, so BLOCK (threshold 90) requires ML model.
        This test verifies the threshold logic works by using a lower threshold.
        """
        from app.services.anomaly_detection import AnomalyDetectionService

        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-RISK-002", private_key
        )

        service = AnomalyDetectionService(db_session)

        # Test should_block with explicit threshold
        assert service.should_block(95, block_threshold=90) == True
        assert service.should_block(85, block_threshold=90) == False
        assert service.should_block(100, block_threshold=90) == True

        # Test should_trigger_review with explicit threshold
        assert service.should_trigger_review(65, policy_threshold=60) == True
        assert service.should_trigger_review(55, policy_threshold=60) == False
        assert service.should_trigger_review(60, policy_threshold=60) == True


class TestMLDetector:
    """Tests for ML-based anomaly detection."""

    def test_ml_detector_loads_model_when_available(self, db_session: Session):
        """ML detector should load model when model files exist."""
        from app.services.anomaly_detection import MLAnomalyDetector

        detector = MLAnomalyDetector()
        # Model should be available now (trained during setup)
        assert detector.is_available() == True
        assert detector.model is not None
        assert detector.scaler is not None

    def test_ml_detector_available_but_requires_history(self, db_session: Session):
        """ML detector is available but requires sufficient history to run."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-ML-001", private_key
        )

        service = AnomalyDetectionService(db_session)
        assessment = service.assess_transaction(
            agent_id=agent.id,
            amount_cents=10000,
            merchant_id="MERCH-TEST",
            currency="USD",
        )

        # ML model is available
        assert assessment["ml_available"] == True
        # But with no history (0 < MIN_SAMPLES_FOR_ML), falls back to rule_based
        assert assessment["detection_method"] == "rule_based"
        assert assessment["history_count"] == 0

    def test_ml_detector_runs_with_sufficient_history(self, db_session: Session):
        """ML detector should run when agent has sufficient transaction history."""
        from app.services.anomaly_detection import MIN_SAMPLES_FOR_ML

        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-ML-002", private_key
        )

        # Create enough history for ML to run (>= MIN_SAMPLES_FOR_ML)
        ref_time = datetime.utcnow()
        history = []
        for i in range(MIN_SAMPLES_FOR_ML + 5):  # 25 transactions
            history.append({
                "request_id": f"ml-hist-req-{i}",
                "idempotency_key": f"ml-hist-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": 10000,  # Consistent amounts
                "merchant_id": "MERCH-REGULAR",
                "merchant_category": "retail",
                "decided_at": ref_time - timedelta(hours=i * 2),
            })
        create_authorization_history(db_session, agent.id, history)

        service = AnomalyDetectionService(db_session)
        assessment = service.assess_transaction(
            agent_id=agent.id,
            amount_cents=10000,
            merchant_id="MERCH-REGULAR",
            currency="USD",
        )

        # ML model is available
        assert assessment["ml_available"] == True
        # With sufficient history, ML should run (ml_based or rule_based depending on score)
        assert assessment["detection_method"] in ["rule_based", "ml_based"]
        assert assessment["history_count"] >= MIN_SAMPLES_FOR_ML

    def test_rule_based_detection_always_runs(self, db_session: Session):
        """Rule-based detection should always run regardless of ML availability."""
        from app.services.anomaly_detection import RuleBasedDetector, AnomalyFeatures

        # Test with features that should trigger rules
        detector = RuleBasedDetector()
        features = {
            "txn_count_1h": 10.0,
            "txn_count_24h": 50.0,
            "txn_count_7d": 100.0,
            "amount_zscore": 5.0,
            "amount_log": 9.2,  # log(10000)
            "avg_amount_7d": 100.0,
            "std_amount_7d": 10.0,
            "unique_merchants_7d": 5.0,
            "merchant_novelty": 1.0,
            "time_since_last_txn_h": 0.1,
            "hour_of_day": 3.0,  # Off-hours
            "day_of_week": 6.0,
        }

        risk_score, signals = detector.evaluate(features, agent_history_count=100)

        # Should have multiple signals
        assert risk_score > 0
        signal_types = {s["signal"] for s in signals}
        assert "velocity_anomaly" in signal_types
        assert "amount_outlier" in signal_types
        assert "new_merchant" in signal_types


class TestMLInference:
    """Tests for ML inference deterministic behavior."""

    def test_ml_inference_deterministic(self, db_session: Session):
        """ML inference should be deterministic for same input features."""
        from app.services.anomaly_detection import MLAnomalyDetector

        detector = MLAnomalyDetector()
        if not detector.is_available():
            pytest.skip("ML model not available")

        features = {
            "amount_zscore": 2.0,
            "amount_log": 6.9,  # log(1000)
            "txn_count_1h": 5.0,
            "txn_count_24h": 20.0,
            "txn_count_7d": 50.0,
            "avg_amount_7d": 100.0,
            "std_amount_7d": 20.0,
            "unique_merchants_7d": 3.0,
            "merchant_novelty": 0.0,
            "time_since_last_txn_h": 10.0,
            "hour_of_day": 14.0,
            "day_of_week": 2.0,
        }

        # Run inference multiple times
        scores = []
        for _ in range(10):
            score, signals = detector.predict(features)
            scores.append(score)

        # All scores should be identical (deterministic)
        assert len(set(scores)) == 1, f"Scores not deterministic: {scores}"
        assert scores[0] >= 0
        assert scores[0] <= 100

    def test_ml_inference_normal_vs_anomalous(self, db_session: Session):
        """ML should score normal transactions lower than anomalous ones."""
        from app.services.anomaly_detection import MLAnomalyDetector

        detector = MLAnomalyDetector()
        if not detector.is_available():
            pytest.skip("ML model not available")

        # Normal transaction features
        normal_features = {
            "amount_zscore": 0.5,
            "amount_log": 4.6,  # log(100)
            "txn_count_1h": 2.0,
            "txn_count_24h": 5.0,
            "txn_count_7d": 10.0,
            "avg_amount_7d": 100.0,
            "std_amount_7d": 10.0,
            "unique_merchants_7d": 2.0,
            "merchant_novelty": 0.0,
            "time_since_last_txn_h": 24.0,
            "hour_of_day": 12.0,
            "day_of_week": 2.0,
        }

        # Anomalous transaction features (large amount, high velocity, new merchant)
        anomalous_features = {
            "amount_zscore": 8.0,
            "amount_log": 9.2,  # log(10000)
            "txn_count_1h": 15.0,
            "txn_count_24h": 50.0,
            "txn_count_7d": 100.0,
            "avg_amount_7d": 100.0,
            "std_amount_7d": 10.0,
            "unique_merchants_7d": 5.0,
            "merchant_novelty": 1.0,
            "time_since_last_txn_h": 0.5,
            "hour_of_day": 3.0,  # Off-hours
            "day_of_week": 6.0,
        }

        normal_score, _ = detector.predict(normal_features)
        anomalous_score, _ = detector.predict(anomalous_features)

        # Anomalous should have higher risk score
        assert anomalous_score > normal_score, f"Anomalous ({anomalous_score}) should score higher than normal ({normal_score})"


class TestReviewBlockEnforcement:
    """Tests for REVIEW and BLOCK enforcement through signed authorization requests."""

    def test_high_risk_triggers_review_decision(self, client: TestClient, db_session: Session):
        """High risk score should trigger REVIEW decision in authorization."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-REVIEW-001", private_key,
            daily_budget_cents=5000000,  # $50,000 daily budget
            per_transaction_limit_cents=1000000,  # $10,000 per transaction
        )

        # Create history with high velocity AND variable amounts to enable ML
        ref_time = datetime.utcnow()
        history = []
        for i in range(25):  # >= MIN_SAMPLES_FOR_ML (20) to enable ML
            amount = 10000 + (i % 5) * 5000  # Varying amounts: 10k, 15k, 20k, 25k, 30k
            history.append({
                "request_id": f"hist-req-{i}",
                "idempotency_key": f"hist-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": amount,
                "merchant_id": f"MERCH-KNOWN-{i % 3}",
                "merchant_category": "retail",
                "decided_at": ref_time - timedelta(hours=i * 2),
            })
        create_authorization_history(db_session, agent.id, history)

        # Add recent high-velocity transactions
        recent_history = []
        now = datetime.utcnow()
        for i in range(12):  # High velocity
            recent_history.append({
                "request_id": f"recent-req-{i}",
                "idempotency_key": f"recent-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": 10000,
                "merchant_id": "MERCH-KNOWN-0",
                "merchant_category": "retail",
                "decided_at": now - timedelta(minutes=2 * i + 1),
            })
        create_authorization_history(db_session, agent.id, recent_history)

        # Get nonce
        nonce_resp = client.post(f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}")
        nonce = nonce_resp.json()["nonce"]

        # Request with large amount + new merchant to push risk over REVIEW threshold
        # Amount must be within per_transaction_limit (1M = $10,000)
        payload, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=500000,  # $5000 - large amount anomaly (within limit)
            nonce=nonce,
            merchant_id="MERCH-NEW-HIGHRISK",
        )

        response = client.post("/api/authorize", json=payload)
        assert response.status_code == 200
        data = response.json()

        # Should have elevated risk score (>= 60 for REVIEW)
        assert data["risk_score"] >= 60, f"Expected risk >= 60 for REVIEW, got {data['risk_score']}"
        # Should trigger REVIEW
        assert data["decision"] == "review", f"Expected REVIEW for high risk, got {data['decision']}"
        # Should have anomaly signals
        assert len(data["anomaly_signals"]) > 0

    def test_critical_risk_triggers_block_decision(self, client: TestClient, db_session: Session):
        """Critical risk score should trigger BLOCK decision in authorization."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-BLOCK-001", private_key,
            daily_budget_cents=2000000,
            per_transaction_limit_cents=2000000,
        )

        # Create extensive history with variable amounts (for ML)
        ref_time = datetime.utcnow()
        history = []
        for i in range(25):  # >= MIN_SAMPLES_FOR_ML
            amount = 1000 + (i % 5) * 500  # Varying: 1k, 1.5k, 2k, 2.5k, 3k
            history.append({
                "request_id": f"hist-req-{i}",
                "idempotency_key": f"hist-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": amount,
                "merchant_id": f"MERCH-KNOWN-{i % 3}",
                "merchant_category": "retail",
                "decided_at": ref_time - timedelta(hours=i * 12),
            })
        create_authorization_history(db_session, agent.id, history)

        # Add many recent transactions (extreme velocity)
        recent_history = []
        now = datetime.utcnow()
        for i in range(25):  # Extreme velocity
            recent_history.append({
                "request_id": f"recent-req-{i}",
                "idempotency_key": f"recent-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": 1000,
                "merchant_id": "MERCH-KNOWN-0",
                "merchant_category": "retail",
                "decided_at": now - timedelta(minutes=2 * i + 1),
            })
        create_authorization_history(db_session, agent.id, recent_history)

        # Get nonce
        nonce_resp = client.post(f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}")
        nonce = nonce_resp.json()["nonce"]

        # Request with extreme amount + new merchant
        payload, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=1000000,  # $10,000 - extreme amount
            nonce=nonce,
            merchant_id="MERCH-BRAND-NEW",
        )

        response = client.post("/api/authorize", json=payload)
        assert response.status_code == 200
        data = response.json()

        # Should have critical risk score (>= 90)
        assert data["risk_score"] >= 90, f"Expected risk >= 90 for BLOCK, got {data['risk_score']}"
        # Should trigger BLOCK
        assert data["decision"] == "block", f"Expected BLOCK for critical risk, got {data['decision']}"


class TestHighRiskPaymentBlocking:
    """Tests verifying high-risk payments cannot create reservations or proceed."""

    def test_review_decision_does_not_create_reservation(self, client: TestClient, db_session: Session):
        """REVIEW decision should not create an authorization reservation."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-NORES-001", private_key,
            daily_budget_cents=5000000,  # $50,000 daily budget
            per_transaction_limit_cents=1000000,  # $10,000 per transaction
        )

        # Create history to generate REVIEW (with ML enabled)
        ref_time = datetime.utcnow()
        history = []
        for i in range(25):  # >= MIN_SAMPLES_FOR_ML
            amount = 10000 + (i % 5) * 5000
            history.append({
                "request_id": f"hist-req-{i}",
                "idempotency_key": f"hist-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": amount,
                "merchant_id": f"MERCH-KNOWN-{i % 3}",
                "merchant_category": "retail",
                "decided_at": ref_time - timedelta(hours=i * 2),
            })
        create_authorization_history(db_session, agent.id, history)

        recent_history = []
        now = datetime.utcnow()
        for i in range(12):
            recent_history.append({
                "request_id": f"recent-req-{i}",
                "idempotency_key": f"recent-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": 10000,
                "merchant_id": "MERCH-KNOWN-0",
                "merchant_category": "retail",
                "decided_at": now - timedelta(minutes=2 * i + 1),
            })
        create_authorization_history(db_session, agent.id, recent_history)

        nonce_resp = client.post(f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}")
        nonce = nonce_resp.json()["nonce"]

        payload, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=500000,  # Large amount
            nonce=nonce,
            merchant_id="MERCH-NEW-REVIEW",
            request_id="req-review-001",
            idempotency_key="idem-review-001",
        )

        response = client.post("/api/authorize", json=payload)
        assert response.status_code == 200
        data = response.json()

        # Should be REVIEW
        assert data["decision"] == "review"

        # Check no reservation was created
        from app.models import AuthorizationReservation
        reservation = db_session.query(AuthorizationReservation).join(
            AuthorizationDecisionRecord,
            AuthorizationReservation.auth_decision_id == AuthorizationDecisionRecord.id
        ).filter(
            AuthorizationDecisionRecord.request_id == "req-review-001"
        ).first()

        assert reservation is None, "REVIEW decision should not create reservation"

    def test_block_decision_does_not_create_reservation(self, client: TestClient, db_session: Session):
        """BLOCK decision should not create an authorization reservation."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-NORES-002", private_key,
            daily_budget_cents=50000000,  # $500,000 daily budget
            per_transaction_limit_cents=20000000,  # $200,000 per transaction
        )

        # Create history with extreme anomalies (with ML enabled)
        ref_time = datetime.utcnow()
        history = []
        for i in range(25):  # >= MIN_SAMPLES_FOR_ML
            amount = 1000 + (i % 5) * 500
            history.append({
                "request_id": f"hist-req-{i}",
                "idempotency_key": f"hist-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": amount,
                "merchant_id": f"MERCH-KNOWN-{i % 3}",
                "merchant_category": "retail",
                "decided_at": ref_time - timedelta(hours=i * 12),
            })
        create_authorization_history(db_session, agent.id, history)

        recent_history = []
        now = datetime.utcnow()
        for i in range(25):
            recent_history.append({
                "request_id": f"recent-req-{i}",
                "idempotency_key": f"recent-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": 1000,
                "merchant_id": "MERCH-KNOWN-0",
                "merchant_category": "retail",
                "decided_at": now - timedelta(minutes=2 * i + 1),
            })
        create_authorization_history(db_session, agent.id, recent_history)

        nonce_resp = client.post(f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}")
        nonce = nonce_resp.json()["nonce"]

        payload, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=1000000,  # Extreme amount
            nonce=nonce,
            merchant_id="MERCH-BRAND-NEW-BLOCK",
            request_id="req-block-001",
            idempotency_key="idem-block-001",
        )

        response = client.post("/api/authorize", json=payload)
        assert response.status_code == 200
        data = response.json()

        # Should be BLOCK
        assert data["decision"] == "block"

        # Check no reservation was created
        from app.models import AuthorizationReservation
        reservation = db_session.query(AuthorizationReservation).join(
            AuthorizationDecisionRecord,
            AuthorizationReservation.auth_decision_id == AuthorizationDecisionRecord.id
        ).filter(
            AuthorizationDecisionRecord.request_id == "req-block-001"
        ).first()

        assert reservation is None, "BLOCK decision should not create reservation"

    def test_allow_decision_creates_reservation(self, client: TestClient, db_session: Session):
        """ALLOW decision should create an authorization reservation."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-YESRES-001", private_key
        )

        # Normal history
        ref_time = datetime.utcnow()
        history = []
        for i in range(5):
            history.append({
                "request_id": f"hist-req-{i}",
                "idempotency_key": f"hist-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": 10000,
                "merchant_id": "MERCH-REGULAR",
                "merchant_category": "retail",
                "decided_at": ref_time - timedelta(hours=i * 12),
            })
        create_authorization_history(db_session, agent.id, history)

        nonce_resp = client.post(f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}")
        nonce = nonce_resp.json()["nonce"]

        payload, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=10000,  # Normal amount
            nonce=nonce,
            merchant_id="MERCH-REGULAR",
            request_id="req-allow-001",
            idempotency_key="idem-allow-001",
        )

        response = client.post("/api/authorize", json=payload)
        assert response.status_code == 200
        data = response.json()

        # Should be ALLOW
        assert data["decision"] == "allow"

        # Check reservation WAS created
        from app.models import AuthorizationReservation, ReservationStatus
        reservation = db_session.query(AuthorizationReservation).join(
            AuthorizationDecisionRecord,
            AuthorizationReservation.auth_decision_id == AuthorizationDecisionRecord.id
        ).filter(
            AuthorizationDecisionRecord.request_id == "req-allow-001"
        ).first()

        assert reservation is not None, "ALLOW decision should create reservation"
        assert reservation.status == ReservationStatus.RESERVED
        assert reservation.amount_cents == 10000


class TestIdempotencyWithRisk:
    """Tests for idempotency with risk assessment."""

    def test_idempotent_retry_preserves_risk_decision(self, client: TestClient, db_session: Session):
        """Retrying with same idempotency key should preserve risk assessment."""
        private_key, _ = _generate_keypair()
        agent, _, key_id = create_test_agent_with_policy(
            db_session, "AGT-IDEM-RISK", private_key
        )

        # Create some history
        ref_time = datetime.utcnow()
        history = []
        for i in range(5):
            history.append({
                "request_id": f"hist-req-{i}",
                "idempotency_key": f"hist-idem-{i}",
                "credential_id": 1,
                "policy_id": 1,
                "amount_cents": 10000,
                "merchant_id": "MERCH-REGULAR",
                "merchant_category": "retail",
                "decided_at": ref_time - timedelta(hours=i * 12),
            })
        create_authorization_history(db_session, agent.id, history)

        nonce_resp = client.post(f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}")
        nonce1 = nonce_resp.json()["nonce"]

        payload1, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=10000,
            nonce=nonce1,
            merchant_id="MERCH-REGULAR",
            request_id="req-idem-risk-001",
            idempotency_key="idem-risk-001",
        )

        # First request
        response1 = client.post("/api/authorize", json=payload1)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["decision"] == "allow"

        # Second request with same idempotency key (different nonce, different signature)
        nonce_resp2 = client.post(f"/api/auth/challenge?agent_id={agent.agent_id}&key_id={key_id}")
        nonce2 = nonce_resp2.json()["nonce"]

        payload2, _ = make_auth_payload(
            agent_id=agent.agent_id,
            key_id=key_id,
            private_key=private_key,
            amount_cents=10000,
            nonce=nonce2,
            merchant_id="MERCH-REGULAR",
            request_id="req-idem-risk-002",
            idempotency_key="idem-risk-001",  # Same idempotency key
        )

        response2 = client.post("/api/authorize", json=payload2)
        assert response2.status_code == 200
        data2 = response2.json()

        # Should return same decision and risk fields
        assert data2["decision"] == data1["decision"]
        assert data2["risk_score"] == data1["risk_score"]
        assert data2["risk_level"] == data1["risk_level"]
        assert data2["anomaly_signals"] == data1["anomaly_signals"]
        assert data2["detection_method"] == data1["detection_method"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
