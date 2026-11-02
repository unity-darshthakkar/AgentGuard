"""Tests for dashboard endpoints."""

from decimal import Decimal
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Agent, AgentStatus, SecurityEvent, SecurityEventType, Transaction, TransactionStatus


def create_test_agent(db: Session, **kwargs) -> Agent:
    """Helper to create a test agent."""
    defaults = {
        "agent_id": "TEST-AGT-001",
        "name": "Test Agent",
        "description": "Test description",
        "status": AgentStatus.ACTIVE,
        "owner_type": "human",
        "owner_name": "Test Owner",
        "owner_email": "test@example.com",
        "daily_limit_usd": Decimal("10000.00"),
        "monthly_limit_usd": Decimal("100000.00"),
    }
    defaults.update(kwargs)
    agent = Agent(**defaults)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def create_test_transaction(db: Session, agent_id: int, **kwargs) -> Transaction:
    """Helper to create a test transaction."""
    defaults = {
        "transaction_id": "TEST-TXN-001",
        "agent_id": agent_id,
        "amount_usd": Decimal("100.00"),
        "currency": "USD",
        "merchant_name": "Test Merchant",
        "merchant_category": "retail",
        "merchant_country": "US",
        "description": "Test transaction",
        "status": TransactionStatus.APPROVED,
        "risk_score": 10,
        "risk_level": "low",
        "decision_reason": "Test reason",
        "requested_at": datetime.utcnow() - timedelta(hours=1),
        "decided_at": datetime.utcnow(),
        "completed_at": datetime.utcnow(),
    }
    defaults.update(kwargs)
    txn = Transaction(**defaults)
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def create_test_security_event(db: Session, agent_id: int, **kwargs) -> SecurityEvent:
    """Helper to create a test security event."""
    defaults = {
        "event_id": "TEST-EVT-001",
        "agent_id": agent_id,
        "transaction_id": None,
        "event_type": SecurityEventType.VELOCITY_ANOMALY,
        "severity": "warning",
        "title": "Test Event",
        "description": "Test description",
        "details_json": '{}',
        "detected_at": datetime.utcnow() - timedelta(hours=1),
        "acknowledged_at": None,
        "acknowledged_by": None,
    }
    defaults.update(kwargs)
    event = SecurityEvent(**defaults)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def test_dashboard_summary_empty(client: TestClient) -> None:
    """Test dashboard summary with empty database."""
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_agents"] == 0
    assert data["active_agents"] == 0
    assert data["total_transactions"] == 0
    assert data["total_volume_usd"] == 0.0


def test_dashboard_summary_with_data(client: TestClient, db_session: Session) -> None:
    """Test dashboard summary with data."""
    # Create agents with different statuses
    agent1 = create_test_agent(db_session, agent_id="AGT-001", status=AgentStatus.ACTIVE)
    agent2 = create_test_agent(db_session, agent_id="AGT-002", status=AgentStatus.ACTIVE)
    agent3 = create_test_agent(db_session, agent_id="AGT-003", status=AgentStatus.SUSPENDED)
    agent4 = create_test_agent(db_session, agent_id="AGT-004", status=AgentStatus.PENDING_REVIEW)

    # Create transactions with different statuses
    create_test_transaction(db_session, agent1.id, transaction_id="TXN-001", status=TransactionStatus.APPROVED,
                           amount_usd=Decimal("100.00"), risk_score=10)
    create_test_transaction(db_session, agent1.id, transaction_id="TXN-002", status=TransactionStatus.APPROVED,
                           amount_usd=Decimal("200.00"), risk_score=20)
    create_test_transaction(db_session, agent2.id, transaction_id="TXN-003", status=TransactionStatus.BLOCKED,
                           amount_usd=Decimal("500.00"), risk_score=85)
    create_test_transaction(db_session, agent3.id, transaction_id="TXN-004", status=TransactionStatus.UNDER_REVIEW,
                           amount_usd=Decimal("300.00"), risk_score=60)

    # Create security events
    create_test_security_event(db_session, agent1.id, event_id="EVT-001", detected_at=datetime.utcnow() - timedelta(hours=12))
    create_test_security_event(db_session, agent2.id, event_id="EVT-002", detected_at=datetime.utcnow() - timedelta(hours=6),
                              acknowledged_at=datetime.utcnow())
    create_test_security_event(db_session, agent3.id, event_id="EVT-003", detected_at=datetime.utcnow() - timedelta(hours=48))

    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    data = response.json()

    # Agent counts
    assert data["total_agents"] == 4
    assert data["active_agents"] == 2
    assert data["suspended_agents"] == 1
    assert data["pending_review_agents"] == 1

    # Transaction counts
    assert data["total_transactions"] == 4
    assert data["approved_transactions"] == 2
    assert data["blocked_transactions"] == 1
    assert data["under_review_transactions"] == 1
    assert data["pending_transactions"] == 0
    assert data["failed_transactions"] == 0

    # Volume
    assert data["total_volume_usd"] == 1100.0  # 100 + 200 + 500 + 300

    # Risk stats
    assert data["avg_risk_score"] == 43.75  # (10 + 20 + 85 + 60) / 4
    assert data["low_risk_transactions"] == 2      # 0-30: risk 10, 20
    assert data["medium_risk_transactions"] == 1   # 31-69: risk 60
    assert data["high_risk_transactions"] == 1     # 70-89: risk 85
    assert data["critical_risk_transactions"] == 0 # 90-100: none

    # Security events
    assert data["recent_security_events"] == 2  # Last 24 hours: EVT-001, EVT-002
    assert data["unacknowledged_events"] == 2  # EVT-001, EVT-003