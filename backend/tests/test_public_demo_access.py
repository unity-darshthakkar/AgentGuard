"""Public demo boundary tests: synthetic reads only, no operational access."""

from app.api.routes import public_demo
from app.core.config import get_settings


def test_anonymous_public_demo_is_read_only_and_synthetic(client):
    assert client.get("/api/public-demo/dashboard/summary").status_code == 200
    assert client.get("/api/public-demo/health").status_code == 200
    agents_response = client.get("/api/public-demo/agents")
    assert agents_response.status_code == 200
    agents = agents_response.json()
    assert agents["items"][0]["agent_id"].startswith("DEMO-")
    assert client.get("/api/public-demo/agents/9001").status_code == 200
    assert client.get("/api/public-demo/transactions").status_code == 200
    assert client.get("/api/public-demo/transactions/9001").status_code == 200
    assert client.get("/api/public-demo/authorize/decisions").status_code == 200
    assert client.get("/api/public-demo/authorize/decisions/demo-request-001").status_code == 200
    assert client.get("/api/public-demo/authorize/reservations").status_code == 200
    assert client.get("/api/public-demo/policies/9001").status_code == 200
    assert client.get("/api/public-demo/security-events").status_code == 200
    assert client.post("/api/public-demo/attack-simulator/run").status_code == 200


def test_anonymous_users_cannot_access_operational_dashboard_or_mutations(client):
    assert client.post("/api/attack-simulator/run").status_code in (401, 422)


def test_public_simulator_rate_limit_can_be_enforced(client):
    public_demo._simulation_windows.clear()
    for _ in range(public_demo._MAX_RUNS_PER_WINDOW):
        assert client.post("/api/public-demo/attack-simulator/run").status_code == 200
    assert client.post("/api/public-demo/attack-simulator/run").status_code == 429


def test_forwarded_ip_headers_do_not_bypass_rate_limit(client):
    public_demo._simulation_windows.clear()
    for index in range(public_demo._MAX_RUNS_PER_WINDOW):
        response = client.post("/api/public-demo/attack-simulator/run", headers={"X-Forwarded-For": f"198.51.100.{index}"})
        assert response.status_code == 200
    assert client.post("/api/public-demo/attack-simulator/run", headers={"X-Forwarded-For": "203.0.113.99"}).status_code == 429


def test_hosted_demo_mode_closes_operational_reads(client, monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO_MODE", "true")
    get_settings.cache_clear()
    try:
        assert client.get("/api/dashboard/summary").status_code in (401, 422)
        assert client.get("/api/agents").status_code in (401, 422)
    finally:
        monkeypatch.delenv("PUBLIC_DEMO_MODE", raising=False)
        get_settings.cache_clear()
