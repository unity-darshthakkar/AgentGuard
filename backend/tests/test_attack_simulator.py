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
    assert by_id["legitimate"]["risk_score"] is None
    assert by_id["legitimate"]["risk_evaluation_reason"] == "not_required_after_policy_authorization"
    assert by_id["compromised"]["decision"] == "block"
    assert by_id["compromised"]["policy_outcome"] == "blocked"
    assert by_id["compromised"]["risk_evaluation_reason"] == "policy_rejected_first"
    assert by_id["impersonation"]["decision"] == "rejected"
    assert by_id["impersonation"]["replay_rejected"] is True
    assert by_id["impersonation"]["risk_evaluation_reason"] == "authentication_rejected_first"
