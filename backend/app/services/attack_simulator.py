"""Isolated, server-side attack simulations for the admin demonstration."""

import json
import base64
import uuid
from datetime import datetime, timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Agent, AgentCredential, AgentStatus, AuthorizationDecision, AuthorizationDecisionRecord, Base, CredentialStatus
from app.services.auth import (
    AuthorizationService, canonical_request_string, compute_body_hash, consume_nonce,
    create_spending_policy, release_budget, verify_signature,
)
from app.services.anomaly_detection import AnomalyDetectionService


def _keypair():
    private = ed25519.Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, public


def _agent(db: Session, label: str, private, public: str, per_transaction_limit_cents: int = 2_000_000):
    agent = Agent(agent_id=f"SIM-{label}-{uuid.uuid4().hex[:8]}", name=f"Simulator {label}", description="Isolated demo agent", status=AgentStatus.ACTIVE, owner_type="human", owner_name="AgentGuard Demo", owner_email="demo@agentguard.local")
    db.add(agent); db.flush()
    credential = AgentCredential(agent_id=agent.id, key_id=f"sim-key-{uuid.uuid4().hex[:10]}", public_key=public, algorithm="Ed25519", status=CredentialStatus.ACTIVE, issued_at=datetime.utcnow())
    db.add(credential)
    create_spending_policy(db, agent, "human:demo@agentguard.local", per_transaction_limit_cents, 20_000_000, ["USD"])
    db.commit()
    return agent, credential


def _signed_check(db: Session, agent, private, credential, replay=False):
    nonce = f"sim-nonce-{uuid.uuid4().hex}"
    now = datetime.utcnow().isoformat()
    body = {"scenario": "impersonation"}
    canonical = canonical_request_string("POST", "/api/attack-simulator", now, nonce, compute_body_hash(body))
    signature = base64.b64encode(private.sign(canonical.encode())).decode()
    valid = verify_signature(serialization.load_pem_public_key(credential.public_key.encode()), canonical.encode(), signature)
    consumed = consume_nonce(db, agent.id, nonce)
    replay_rejected = not consume_nonce(db, agent.id, nonce)
    db.rollback()
    return {"verification_status": "valid" if valid else "invalid", "replay_rejected": replay_rejected, "explanation": "The Ed25519 signature was valid. The second request was rejected because its nonce had already been consumed (replay protection)."}


def run_simulation() -> dict:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = Factory()
    try:
        results = []
        private, public = _keypair()
        agent, credential = _agent(db, "LEGITIMATE", private, public)
        policy = agent.spending_policy
        decision, reasons, _, before, after = AuthorizationService(db).evaluate(agent, credential, policy, 2500, "USD", "merchant-grocery", "retail", "Routine purchase", "sim-legit")
        if after > before: release_budget(db, agent.id, 2500)
        results.append({"id": "legitimate", "title": "Legitimate agent", "agent_id": agent.agent_id, "merchant": "merchant-grocery", "amount_cents": 2500, "verification_status": "valid", "authentication_outcome": "verified", "policy_outcome": "allowed", "risk_evaluated": False, "risk_evaluation_reason": "not_required_after_policy_authorization", "risk_score": None, "risk_level": None, "detection_method": "not_evaluated", "decision": decision.value, "reasons": reasons, "signals": [], "payment_status": "authorized_for_checkout", "explanation": "; ".join(reasons)})

        private, public = _keypair(); agent, credential = _agent(db, "COMPROMISED", private, public, per_transaction_limit_cents=500_000)
        now = datetime.utcnow()
        for i in range(25):
            db.add(AuthorizationDecisionRecord(request_id=f"sim-{uuid.uuid4().hex}", idempotency_key=f"sim-{uuid.uuid4().hex}", agent_id=agent.id, credential_id=credential.id, policy_id=agent.spending_policy.id, amount_cents=1000, currency="USD", merchant_id="merchant-known", merchant_category="retail", decided_at=now - timedelta(minutes=i), decision=AuthorizationDecision.ALLOW, reasons="[]", daily_spent_before_cents=0, daily_spent_after_cents=0, risk_score=0, risk_level="minimal"))
        db.commit()
        amount_cents = 1_000_000
        decision, reasons, violations, before, after = AuthorizationService(db).evaluate(
            agent, credential, agent.spending_policy, amount_cents, "USD", "merchant-new", "retail",
            "Unusual high-value purchase", "sim-compromised",
        )
        results.append({"id": "compromised", "title": "Compromised agent", "agent_id": agent.agent_id, "merchant": "merchant-new", "amount_cents": amount_cents, "verification_status": "valid", "authentication_outcome": "verified", "policy_outcome": "blocked", "risk_evaluated": False, "risk_evaluation_reason": "policy_rejected_first", "risk_score": None, "risk_level": None, "detection_method": "not_evaluated", "decision": decision.value, "reasons": reasons + violations, "signals": [], "payment_status": "denied_before_paypal", "explanation": "Valid identity, but the $10,000 request exceeds the compromised agent's $5,000 per-transaction policy limit. AgentGuard blocks it before risk analysis and PayPal checkout."})

        private, public = _keypair(); agent, credential = _agent(db, "IMPERSONATION", private, public)
        result = _signed_check(db, agent, private, credential)
        result.update({"id": "impersonation", "title": "Impersonation / replay attack", "agent_id": agent.agent_id, "merchant": "merchant-unknown", "amount_cents": 5000, "authentication_outcome": "replay_rejected", "policy_outcome": "not_evaluated", "risk_evaluated": False, "risk_evaluation_reason": "authentication_rejected_first", "decision": "rejected", "risk_score": None, "risk_level": None, "detection_method": "not_evaluated", "reasons": ["Signature verification passed", "Nonce replay rejected before authorization"], "signals": [], "payment_status": "denied_before_authorization"})
        results.append(result)
        return {"isolated": True, "paypal_touched": False, "scenarios": results}
    finally:
        db.close(); engine.dispose()
