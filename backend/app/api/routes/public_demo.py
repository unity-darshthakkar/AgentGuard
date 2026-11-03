"""Explicit, read-only public demo surface.

This router never reads operational tables and never accepts payment data. It is
intended for a public hosted demonstration only.
"""

from collections import defaultdict
from time import monotonic
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from app.services.attack_simulator import run_simulation

router = APIRouter(prefix="/public-demo", tags=["public-demo"])
_simulation_windows: dict[str, list[float]] = defaultdict(list)
_WINDOW_SECONDS = 60
_MAX_RUNS_PER_WINDOW = 6


def _page(items: list[dict[str, Any]], page: int = 1, page_size: int = 20) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 50)
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": len(items), "page": page,
            "page_size": page_size, "total_pages": max(1, (len(items) + page_size - 1) // page_size)}


def _fixtures() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    agent = {"id": 9001, "agent_id": "DEMO-AGENT-001", "name": "Synthetic Concierge", "description": "Public demonstration agent", "status": "active", "owner_type": "demo", "owner_name": "AgentGuard Demo", "owner_email": "demo@example.invalid", "owner_contact": None, "daily_limit_usd": 2000, "monthly_limit_usd": 20000, "allowed_merchant_categories": "retail", "blocked_merchant_categories": None, "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00", "last_active_at": "2026-11-01T12:00:00"}
    transaction = {"id": 9001, "transaction_id": "DEMO-TXN-001", "agent_id": 9001, "amount_usd": 25.0, "currency": "USD", "merchant_name": "Demo Market", "merchant_category": "retail", "merchant_country": "US", "description": "Synthetic demonstration transaction", "status": "approved", "risk_score": 12, "risk_level": "low", "decision_reason": "Synthetic demo policy approval", "requested_at": "2026-11-01T12:00:00", "decided_at": "2026-11-01T12:00:01", "completed_at": None}
    decision = {"id": 9001, "request_id": "demo-request-001", "idempotency_key": "demo-idempotency-001", "agent_id": 9001, "credential_id": None, "policy_id": None, "amount_cents": 2500, "currency": "USD", "merchant_id": "demo-market", "merchant_category": "retail", "description": "Synthetic demonstration authorization", "decision": "allow", "reasons": ["Synthetic demo data"], "policy_violations": [], "daily_spent_before_cents": 0, "daily_spent_after_cents": 2500, "decided_at": "2026-11-01T12:00:01"}
    event = {"id": 9001, "event_id": "demo-event-001", "agent_id": 9001, "transaction_id": 9001, "event_type": "new_merchant", "severity": "info", "title": "Synthetic demo event", "description": "This event is public demonstration data.", "details_json": None, "detected_at": "2026-11-01T12:00:01", "acknowledged_at": None, "acknowledged_by": None}
    summary = {"total_agents": 1, "active_agents": 1, "suspended_agents": 0, "pending_review_agents": 0, "total_transactions": 1, "approved_transactions": 1, "blocked_transactions": 0, "under_review_transactions": 0, "pending_transactions": 0, "failed_transactions": 0, "total_volume_usd": 25.0, "avg_risk_score": 12.0, "low_risk_transactions": 1, "medium_risk_transactions": 0, "high_risk_transactions": 0, "critical_risk_transactions": 0, "recent_security_events": 1, "unacknowledged_events": 1}
    return summary, [agent], [transaction], [decision], [event]


@router.get("/dashboard/summary")
def demo_summary():
    return _fixtures()[0]


@router.get("/agents")
def demo_agents(page: int = 1, page_size: int = 20, status: str | None = None):
    items = _fixtures()[1]
    return _page([x for x in items if not status or x["status"] == status], page, page_size)


@router.get("/agents/{agent_id}")
def demo_agent(agent_id: int):
    return _fixtures()[1][0]


@router.get("/transactions")
def demo_transactions(page: int = 1, page_size: int = 20, agent_id: int | None = None, status: str | None = None, min_risk: int | None = None, max_risk: int | None = None):
    return _page(_fixtures()[2], page, page_size)


@router.get("/transactions/{transaction_id}")
def demo_transaction(transaction_id: int):
    item = dict(_fixtures()[2][0])
    item["agent"] = _fixtures()[1][0]
    item["security_events"] = [_fixtures()[4][0]]
    return item


@router.get("/authorize/decisions")
def demo_decisions(page: int = 1, page_size: int = 20, agent_id: str | None = None, decision: str | None = None):
    return _page(_fixtures()[3], page, page_size)


@router.get("/authorize/decisions/{request_id}")
def demo_decision(request_id: str):
    return _fixtures()[3][0]


@router.get("/authorize/reservations")
def demo_reservations(page: int = 1, page_size: int = 20, agent_id: int | None = None, status: str | None = None):
    return _page([], page, page_size)


@router.get("/authorize/reservations/{auth_decision_id}")
def demo_reservation(auth_decision_id: int):
    raise HTTPException(status_code=404, detail="No public demo reservation")


@router.get("/policies/{agent_id}")
def demo_policy(agent_id: str):
    return {"id": 9001, "agent_id": 9001, "owner_id": "demo", "per_transaction_limit_cents": 200000, "daily_budget_cents": 2000000, "allowed_currencies": ["USD"], "allowed_merchant_ids": None, "blocked_merchant_ids": None, "status": "active", "effective_at": "2026-01-01T00:00:00", "expires_at": None, "revoked_at": None, "revoked_by": None, "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"}


@router.get("/health")
def demo_health():
    return {"status": "healthy", "version": "public-demo", "database": "synthetic", "timestamp": "2026-11-01T12:00:00"}


@router.get("/security-events")
def demo_events(page: int = 1, page_size: int = 20, agent_id: int | None = None, transaction_id: int | None = None, event_type: str | None = None, severity: str | None = None):
    return _page(_fixtures()[4], page, page_size)


@router.post("/attack-simulator/run")
def demo_simulation(request: Request):
    now = monotonic()
    client = request.client.host if request.client else "unknown"
    recent = [t for t in _simulation_windows[client] if now - t < _WINDOW_SECONDS]
    if len(recent) >= _MAX_RUNS_PER_WINDOW:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Demo simulation rate limit exceeded")
    recent.append(now)
    _simulation_windows[client] = recent
    result = run_simulation()
    if result.get("isolated") is not True or result.get("paypal_touched") is not False:
        raise HTTPException(status_code=503, detail="Demo simulator isolation check failed")
    return result
