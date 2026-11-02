"""Tests for transaction endpoints."""

from decimal import Decimal
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Agent, AgentStatus, Transaction, TransactionStatus


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


def test_list_transactions_empty(client: TestClient) -> None:
    """Test listing transactions when database is empty."""
    response = client.get("/api/transactions")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_list_transactions_with_data(client: TestClient, db_session: Session) -> None:
    """Test listing transactions with data."""
    agent = create_test_agent(db_session)
    create_test_transaction(db_session, agent.id, transaction_id="TEST-TXN-001", amount_usd=Decimal("100.00"))
    create_test_transaction(db_session, agent.id, transaction_id="TEST-TXN-002", amount_usd=Decimal("200.00"),
                           status=TransactionStatus.BLOCKED)

    response = client.get("/api/transactions")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    # Most recent first
    assert data["items"][0]["transaction_id"] == "TEST-TXN-002"
    assert data["items"][1]["transaction_id"] == "TEST-TXN-001"


def test_list_transactions_pagination(client: TestClient, db_session: Session) -> None:
    """Test transaction pagination."""
    agent = create_test_agent(db_session)
    for i in range(5):
        create_test_transaction(db_session, agent.id, transaction_id=f"TEST-TXN-{i:03d}")

    response = client.get("/api/transactions?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["total_pages"] == 3


def test_list_transactions_agent_filter(client: TestClient, db_session: Session) -> None:
    """Test filtering transactions by agent."""
    agent1 = create_test_agent(db_session, agent_id="AGT-001")
    agent2 = create_test_agent(db_session, agent_id="AGT-002")
    create_test_transaction(db_session, agent1.id, transaction_id="TXN-001")
    create_test_transaction(db_session, agent2.id, transaction_id="TXN-002")

    response = client.get(f"/api/transactions?agent_id={agent1.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["agent_id"] == agent1.id


def test_list_transactions_status_filter(client: TestClient, db_session: Session) -> None:
    """Test filtering transactions by status."""
    agent = create_test_agent(db_session)
    create_test_transaction(db_session, agent.id, transaction_id="TXN-001", status=TransactionStatus.APPROVED)
    create_test_transaction(db_session, agent.id, transaction_id="TXN-002", status=TransactionStatus.BLOCKED)
    create_test_transaction(db_session, agent.id, transaction_id="TXN-003", status=TransactionStatus.APPROVED)

    response = client.get("/api/transactions?status=blocked")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "blocked"


def test_list_transactions_risk_filter(client: TestClient, db_session: Session) -> None:
    """Test filtering transactions by risk score range."""
    agent = create_test_agent(db_session)
    create_test_transaction(db_session, agent.id, transaction_id="TXN-001", risk_score=10)
    create_test_transaction(db_session, agent.id, transaction_id="TXN-002", risk_score=50)
    create_test_transaction(db_session, agent.id, transaction_id="TXN-003", risk_score=90)

    response = client.get("/api/transactions?min_risk=40&max_risk=60")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["risk_score"] == 50


def test_get_transaction_detail(client: TestClient, db_session: Session) -> None:
    """Test getting transaction detail with agent and events."""
    agent = create_test_agent(db_session)
    txn = create_test_transaction(db_session, agent.id)

    response = client.get(f"/api/transactions/{txn.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == txn.id
    assert data["transaction_id"] == "TEST-TXN-001"
    assert data["agent"] is not None
    assert data["agent"]["id"] == agent.id
    assert "security_events" in data


def test_get_transaction_not_found(client: TestClient) -> None:
    """Test getting non-existent transaction returns 404."""
    response = client.get("/api/transactions/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Transaction not found"