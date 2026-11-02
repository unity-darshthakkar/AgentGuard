import os

os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("ADMIN_API_KEY", "sim-test-key")

from app.services.attack_simulator import run_simulation


def test_simulator_runs_isolated_real_scenarios():
    result = run_simulation()
    by_id = {scenario["id"]: scenario for scenario in result["scenarios"]}
    assert result["isolated"] is True
    assert result["paypal_touched"] is False
    assert by_id["legitimate"]["decision"] == "allow"
    assert by_id["legitimate"]["verification_status"] == "valid"
    assert by_id["compromised"]["decision"] in {"review", "block"}
    assert by_id["compromised"]["risk_score"] >= 60
    assert by_id["impersonation"]["decision"] == "rejected"
    assert by_id["impersonation"]["replay_rejected"] is True
