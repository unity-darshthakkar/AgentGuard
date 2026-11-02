"""Tests for agent endpoints."""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Agent, AgentStatus


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
        "owner_contact": None,
        "daily_limit_usd": Decimal("1000.00"),
        "monthly_limit_usd": Decimal("10000.00"),
        "allowed_merchant_categories": '["retail", "software"]',
        "blocked_merchant_categories": '["gambling"]',
    }
    defaults.update(kwargs)
    agent = Agent(**defaults)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def test_list_agents_empty(client: TestClient) -> None:
    """Test listing agents when database is empty."""
    response = client.get("/api/agents")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 20


def test_list_agents_with_data(client: TestClient, db_session: Session) -> None:
    """Test listing agents with data."""
    create_test_agent(db_session, agent_id="TEST-AGT-001", name="Agent One")
    create_test_agent(db_session, agent_id="TEST-AGT-002", name="Agent Two", status=AgentStatus.SUSPENDED)

    response = client.get("/api/agents")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    # Check both agents are present (order not guaranteed when created_at is same)
    names = {item["name"] for item in data["items"]}
    assert names == {"Agent One", "Agent Two"}


def test_list_agents_pagination(client: TestClient, db_session: Session) -> None:
    """Test agent pagination."""
    for i in range(5):
        create_test_agent(db_session, agent_id=f"TEST-AGT-{i:03d}", name=f"Agent {i}")

    response = client.get("/api/agents?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total_pages"] == 3


def test_list_agents_status_filter(client: TestClient, db_session: Session) -> None:
    """Test filtering agents by status."""
    create_test_agent(db_session, agent_id="TEST-AGT-001", status=AgentStatus.ACTIVE)
    create_test_agent(db_session, agent_id="TEST-AGT-002", status=AgentStatus.SUSPENDED)
    create_test_agent(db_session, agent_id="TEST-AGT-003", status=AgentStatus.ACTIVE)

    response = client.get("/api/agents?status=active")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert all(a["status"] == "active" for a in data["items"])


def test_get_agent_detail(client: TestClient, db_session: Session) -> None:
    """Test getting agent detail."""
    agent = create_test_agent(db_session, agent_id="TEST-AGT-001")

    response = client.get(f"/api/agents/{agent.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == agent.id
    assert data["agent_id"] == "TEST-AGT-001"
    assert data["name"] == "Test Agent"
    assert "transaction_count" in data
    assert "total_volume_usd" in data


def test_get_agent_not_found(client: TestClient) -> None:
    """Test getting non-existent agent returns 404."""
    response = client.get("/api/agents/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found"