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
    assert by_id["revoked"]["decision"] == "rejected"
    assert by_id["revoked"]["authentication_outcome"] == "credential_rejected"
    assert by_id["revoked"]["risk_evaluation_reason"] == "authentication_rejected_first"
    assert by_id["impersonation"]["decision"] == "rejected"
    assert by_id["impersonation"]["replay_rejected"] is True
    assert by_id["impersonation"]["risk_evaluation_reason"] == "authentication_rejected_first"


def test_all_simulator_modes_use_isolated_backend_outcomes():
    from app.services.attack_simulator import run_simulation

    mode1 = run_simulation(1)
    mode2 = run_simulation(2)
    mode3 = run_simulation(3)
    assert [mode1["mode"], mode2["mode"], mode3["mode"]] == [1, 2, 3]
    for result in (mode1, mode2, mode3):
        assert result["isolated"] is True
        assert result["paypal_touched"] is False
    assert [scenario["decision"] for scenario in mode1["scenarios"]] == ["allow", "rejected", "rejected"]
    assert [scenario["decision"] for scenario in mode2["scenarios"]] == ["allow", "block", "block"]
    assert mode2["scenarios"][2]["policy_outcome"] == "blocked"
    assert mode3["scenarios"][0]["decision"] == "allow"
    assert mode3["scenarios"][1]["decision"] in ("review", "block")
    assert mode3["scenarios"][2]["decision"] in ("review", "block")
    assert all(scenario["risk_evaluated"] for scenario in mode3["scenarios"])


def test_simulator_mode_rotation():
    import app.services.attack_simulator as simulator

    simulator._next_mode = 1
    assert [simulator.run_simulation()["mode"] for _ in range(4)] == [1, 2, 3, 1]
