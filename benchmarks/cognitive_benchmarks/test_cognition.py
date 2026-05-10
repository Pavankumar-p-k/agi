import pytest
from brain.MetaCognitionEngine import ExecutiveMetaCognitionV3

def test_trust_drift_limits():
    meta = ExecutiveMetaCognitionV3()
    
    trust = meta.trust_drift()
    assert 0.0 <= trust <= 1.0, "Trust metric must fall in valid bound."
    
    regret = meta.strategic_regret()
    assert 0.0 <= regret <= 1.0, "Regret metric must be calibrated."
    
    score = meta.benchmark_self_scoring()
    assert "trust" in score
    assert "regret" in score
    assert "cognition" in score


def test_multi_step_and_counterfactual_signals():
    meta = ExecutiveMetaCognitionV3()
    audit = meta.self_audit()
    assert "drift_count" in audit
    assert isinstance(audit["stub_functions"], list)

    identity = meta.identity_consistency()
    strategic = meta.strategic_effectiveness()
    assert 0.0 <= identity <= 1.0
    assert 0.0 <= strategic <= 1.0


def test_interruption_recovery_and_governance_integrity():
    meta = ExecutiveMetaCognitionV3()
    # Simulate previous failed patch and ensure scoring reflects regret.
    meta.last_patch_result = {"validated": False, "status": "ROLLBACK"}
    assert meta.interruption_quality() <= 0.6
    assert meta.strategic_regret() >= 0.5
    assert 0.0 <= meta.governance_integrity() <= 1.0
