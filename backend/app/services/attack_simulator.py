"""Isolated, server-side attack simulations for the admin demonstration."""

import json
import base64
import uuid
import threading
from datetime import datetime, timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Agent, AgentCredential, AgentStatus, AuthorizationDecision, AuthorizationDecisionRecord, Base, CredentialStatus
from app.services.auth import (
    AuthorizationService, canonical_request_string, compute_body_hash, consume_nonce,
    check_credential_valid, create_spending_policy, record_authorization_decision,
    release_budget, verify_signature,
)
from app.services.anomaly_detection import AnomalyDetectionService, normalize_risk_score


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


def _run_mode1() -> dict:
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

        private, public = _keypair(); agent, credential = _agent(db, "REVOKED", private, public)
        credential.status = CredentialStatus.REVOKED
        db.commit()
        valid, reason = check_credential_valid(credential)
        results.append({"id": "revoked", "title": "Revoked agent credential", "agent_id": agent.agent_id, "merchant": "merchant-grocery", "amount_cents": 2500, "verification_status": "invalid", "authentication_outcome": "credential_rejected", "policy_outcome": "not_evaluated", "risk_evaluated": False, "risk_evaluation_reason": "authentication_rejected_first", "risk_score": None, "risk_level": None, "detection_method": "not_evaluated", "decision": "rejected", "reasons": [reason], "signals": [], "payment_status": "denied_before_authorization", "explanation": "The registered agent credential was revoked, so authorization was rejected before policy or risk evaluation."})

        private, public = _keypair(); agent, credential = _agent(db, "IMPERSONATION", private, public)
        result = _signed_check(db, agent, private, credential)
        result.update({"id": "impersonation", "title": "Impersonation / replay attack", "agent_id": agent.agent_id, "merchant": "merchant-unknown", "amount_cents": 5000, "authentication_outcome": "replay_rejected", "policy_outcome": "not_evaluated", "risk_evaluated": False, "risk_evaluation_reason": "authentication_rejected_first", "decision": "rejected", "risk_score": None, "risk_level": None, "detection_method": "not_evaluated", "reasons": ["Signature verification passed", "Nonce replay rejected before authorization"], "signals": [], "payment_status": "denied_before_authorization"})
        results.append(result)
        return {"isolated": True, "paypal_touched": False, "scenarios": results}
    finally:
        db.close(); engine.dispose()


_mode_lock = threading.Lock()
_next_mode = 1


def _scenario(agent, amount_cents, merchant_id, description, decision, reasons, violations=None,
              authentication_outcome="verified", policy_outcome="allowed", risk=None,
              payment_status="authorized_for_checkout"):
    risk = risk or {}
    return {
        "id": str(uuid.uuid4()), "title": description, "agent_id": agent.agent_id,
        "merchant": merchant_id, "amount_cents": amount_cents,
        "verification_status": "valid" if authentication_outcome == "verified" else "invalid",
        "authentication_outcome": authentication_outcome, "policy_outcome": policy_outcome,
        "risk_evaluated": bool(risk), "risk_evaluation_reason": risk.get("reason"),
        "risk_score": risk.get("risk_score"), "risk_level": risk.get("risk_level"),
        "detection_method": risk.get("detection_method", "not_evaluated"),
        "decision": decision.value if isinstance(decision, AuthorizationDecision) else decision,
        "reasons": reasons + (violations or []), "signals": risk.get("anomaly_signals", []),
        "payment_status": payment_status,
        "explanation": "; ".join(reasons + (violations or [])),
    }


def _new_sim_agent(db, label, limit=500000, allowed_merchants=None):
    private, public = _keypair()
    agent, credential = _agent(db, label, private, public, per_transaction_limit_cents=limit)
    if allowed_merchants is not None:
        credential_policy = agent.spending_policy
        credential_policy.allowed_merchant_ids = json.dumps(allowed_merchants)
        db.commit()
    return agent, credential, private


def _evaluate(db, agent, credential, amount, merchant, description, key):
    decision, reasons, violations, before, after = AuthorizationService(db).evaluate(
        agent, credential, agent.spending_policy, amount, "USD", merchant, "retail", description, key
    )
    risk = None
    if decision == AuthorizationDecision.ALLOW:
        assessment = AnomalyDetectionService(db).assess_transaction(agent.id, amount, merchant, "USD")
        score = normalize_risk_score(assessment["risk_score"])
        risk = {**assessment, "risk_score": score, "risk_level": assessment["risk_severity"]}
        if score >= 90:
            decision = AuthorizationDecision.BLOCK
            reasons.append(f"Anomaly detection: Risk score {score} exceeds block threshold")
        elif score >= 60:
            decision = AuthorizationDecision.REVIEW
            reasons.append(f"Anomaly detection: Risk score {score} triggers review")
        if decision != AuthorizationDecision.ALLOW and after > before:
            release_budget(db, agent.id, amount)
            after = before
    if decision == AuthorizationDecision.ALLOW:
        release_budget(db, agent.id, amount)
    return decision, reasons, violations, before, after, risk


def _run_mode2():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        agent, credential, _ = _new_sim_agent(db, "POLICY", limit=500000, allowed_merchants=["merchant-grocery"])
        results = []
        d, r, v, _, _, risk = _evaluate(db, agent, credential, 5000, "merchant-grocery", "Legitimate $50 payment", "mode2-legit")
        results.append(_scenario(agent, 5000, "merchant-grocery", "Legitimate $50 payment", d, r, v, risk=risk))
        d, r, v, _, _, risk = _evaluate(db, agent, credential, 1000000, "merchant-grocery", "$10,000 over policy limit", "mode2-limit")
        results.append(_scenario(agent, 1000000, "merchant-grocery", "$10,000 over policy limit", d, r, v, risk=risk, policy_outcome="blocked", payment_status="denied_before_paypal"))
        d, r, v, _, _, risk = _evaluate(db, agent, credential, 5000, "merchant-restricted", "Restricted merchant request", "mode2-merchant")
        results.append(_scenario(agent, 5000, "merchant-restricted", "Restricted merchant request", d, r, v, risk=risk, policy_outcome="blocked", payment_status="denied_before_paypal"))
        return {"mode": 2, "mode_name": "Spending & Policy", "isolated": True, "paypal_touched": False, "scenarios": results}
    finally:
        db.close(); engine.dispose()


def _run_mode3():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        results = []
        normal_agent, normal_credential, _ = _new_sim_agent(db, "RISK-NORMAL", limit=5000000)
        d, r, v, _, _, risk = _evaluate(db, normal_agent, normal_credential, 3000, "merchant-regular", "Normal $30 transaction", "mode3-normal")
        results.append(_scenario(normal_agent, 3000, "merchant-regular", "Normal $30 transaction", d, r, v, risk=risk))

        def seed_history(label):
            agent, credential, _ = _new_sim_agent(db, label, limit=5000000)
            now = datetime.utcnow()
            for i in range(25):
                db.add(AuthorizationDecisionRecord(
                    request_id=f"risk-history-{uuid.uuid4().hex}", idempotency_key=f"risk-history-{uuid.uuid4().hex}",
                    agent_id=agent.id, credential_id=credential.id, policy_id=agent.spending_policy.id,
                    amount_cents=3000 if i % 2 else 3500, currency="USD", merchant_id="merchant-regular",
                    merchant_category="retail", decided_at=now - timedelta(minutes=i),
                    decision=AuthorizationDecision.ALLOW, reasons="[]", daily_spent_before_cents=0,
                    daily_spent_after_cents=0, risk_score=0, risk_level="minimal"))
            db.commit()
            return agent, credential

        velocity_agent, velocity_credential = seed_history("RISK-VELOCITY")
        d, r, v, _, _, risk = _evaluate(db, velocity_agent, velocity_credential, 3000, "merchant-velocity", "Suspicious transaction velocity", "mode3-velocity")
        results.append(_scenario(velocity_agent, 3000, "merchant-velocity", "Suspicious transaction velocity", d, r, v, risk=risk, payment_status="denied_before_paypal" if d != AuthorizationDecision.ALLOW else "authorized_for_checkout"))

        outlier_agent, outlier_credential = seed_history("RISK-OUTLIER")
        d, r, v, _, _, risk = _evaluate(db, outlier_agent, outlier_credential, 500000, "merchant-outlier", "Amount outlier", "mode3-outlier")
        results.append(_scenario(outlier_agent, 500000, "merchant-outlier", "Amount outlier", d, r, v, risk=risk, payment_status="denied_before_paypal" if d != AuthorizationDecision.ALLOW else "authorized_for_checkout"))
        return {"mode": 3, "mode_name": "Behavioral & Risk", "isolated": True, "paypal_touched": False, "scenarios": results}
    finally:
        db.close(); engine.dispose()


def run_simulation(mode: int | None = None) -> dict:
    """Run the next isolated mode; all outcomes come from current services."""
    global _next_mode
    if mode is None:
        with _mode_lock:
            mode = _next_mode
            _next_mode = mode % 3 + 1
    if mode not in (1, 2, 3):
        raise ValueError("simulation mode must be 1, 2, or 3")
    if mode == 1:
        result = _run_mode1()
        result.update({"mode": 1, "mode_name": "Identity & Access"})
        return result
    return _run_mode2() if mode == 2 else _run_mode3()
