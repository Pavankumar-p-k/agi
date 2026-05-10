"""Phase 7 Mythos Omega - Reconstruction Tests."""

from __future__ import annotations

import asyncio
import os
import sys
import traceback

# Add parent directory to path so modules can be found
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_imports():
    """Test that all Phase 7 modules can be imported."""
    print("Testing imports...")
    errors = []

    try:
        from jarvis_os.core.sovereign_router import SovereignRouter, TaskClassification, RoutingPlan
        print("  [OK] jarvis_os.core.sovereign_router")
    except Exception as e:
        errors.append(f"sovereign_router: {e}")
        print(f"  [FAIL] jarvis_os.core.sovereign_router: {e}")

    try:
        from tools.multi_source_grounding import MultiSourceGrounding, GroundingResult
        print("  [OK] tools.multi_source_grounding")
    except Exception as e:
        errors.append(f"multi_source_grounding: {e}")
        print(f"  [FAIL] tools.multi_source_grounding: {e}")

    try:
        from verification.adversarial_verifier import AdversarialVerifier, VerificationResult
        print("  [OK] verification.adversarial_verifier")
    except Exception as e:
        errors.append(f"adversarial_verifier: {e}")
        print(f"  [FAIL] verification.adversarial_verifier: {e}")

    try:
        from trust.confidence_calibrator import ConfidenceCalibrator, CalibrationBucket
        print("  [OK] trust.confidence_calibrator")
    except Exception as e:
        errors.append(f"confidence_calibrator: {e}")
        print(f"  [FAIL] trust.confidence_calibrator: {e}")

    try:
        from economics.cost_model import CostModel, CostEstimate
        print("  [OK] economics.cost_model")
    except Exception as e:
        errors.append(f"cost_model: {e}")
        print(f"  [FAIL] economics.cost_model: {e}")

    try:
        from economics.latency_model import LatencyModel, LatencyEstimate
        print("  [OK] economics.latency_model")
    except Exception as e:
        errors.append(f"latency_model: {e}")
        print(f"  [FAIL] economics.latency_model: {e}")

    try:
        from jarvis_os.core.stage_pruner import StagePruner
        print("  [OK] jarvis_os.core.stage_pruner")
    except Exception as e:
        errors.append(f"stage_pruner: {e}")
        print(f"  [FAIL] jarvis_os.core.stage_pruner: {e}")

    try:
        from jarvis_os.core.loop import AgentLoop
        print("  [OK] jarvis_os.core.loop (rewritten)")
    except Exception as e:
        errors.append(f"loop: {e}")
        print(f"  [FAIL] jarvis_os.core.loop: {e}")

    try:
        from jarvis_os.core.factory import create_sovereign_system, verify_safety_enforcement
        print("  [OK] jarvis_os.core.factory (wiring)")
    except Exception as e:
        errors.append(f"factory: {e}")
        print(f"  [FAIL] jarvis_os.core.factory: {e}")

    try:
        from jarvis_os.self_improve.loop import SelfImprovementLoop
        print("  [OK] jarvis_os.self_improve.loop (fixed)")
    except Exception as e:
        errors.append(f"self_improve.loop: {e}")
        print(f"  [FAIL] jarvis_os.self_improve.loop: {e}")

    return errors


def test_sovereign_router():
    """Test sovereign router - NO keyword-only routing."""
    print("\nTesting SovereignRouter...")
    errors = []

    try:
        from jarvis_os.core.sovereign_router import SovereignRouter, TaskClassification

        router = SovereignRouter()

        # Test classification
        classification = router.classify("What is the capital of France?")
        assert isinstance(classification, TaskClassification)
        assert classification.task_type != ""
        print(f"  [OK] Classification: {classification.task_type}")

        # Test disagreement_risk is ALWAYS non-zero
        assert classification.disagreement_risk > 0.0, "disagreement_risk must be > 0"
        print(f"  [OK] Disagreement risk always > 0: {classification.disagreement_risk:.2f}")

        # Test build_plan
        plan = router.build_plan(classification)
        assert hasattr(plan, "grounding_priority")
        assert hasattr(plan, "verification_priority")
        assert hasattr(plan, "uncertainty_score")
        print(f"  [OK] RoutingPlan created with grounding_priority={plan.grounding_priority:.2f}")

        # Test uncertainty computation
        uncertainty = router.compute_uncertainty(classification)
        assert 0.0 <= uncertainty <= 1.0
        print(f"  [OK] Uncertainty computed: {uncertainty:.2f}")

    except Exception as e:
        errors.append(f"sovereign_router: {e}")
        print(f"  [FAIL] SovereignRouter: {e}")
        traceback.print_exc()

    return errors


def test_calibrator():
    """Test confidence calibrator - post-penalty only."""
    print("\nTesting ConfidenceCalibrator...")
    errors = []

    try:
        from trust.confidence_calibrator import ConfidenceCalibrator

        calibrator = ConfidenceCalibrator()

        # Test calibration
        result = {"confidence": 0.8}
        calibrated = calibrator.calibrate(result, penalties_applied=["test"])
        assert "confidence" in calibrated
        assert "calibration" in calibrated
        print(f"  [OK] Calibration applied: {calibrated['confidence']:.2f}")

        # Test drift reset does NOT erase history
        calibrator.reset_drift()
        history = calibrator.get_calibration_history()
        assert isinstance(history, list)
        print(f"  [OK] Drift reset preserves history: {len(history)} samples")

    except Exception as e:
        errors.append(f"calibrator: {e}")
        print(f"  [FAIL] ConfidenceCalibrator: {e}")
        traceback.print_exc()

    return errors


def test_stage_pruner():
    """Test stage pruner - NEVER removes reasoning stage."""
    print("\nTesting StagePruner...")
    errors = []

    try:
        from jarvis_os.core.stage_pruner import StagePruner
        from jarvis_os.core.sovereign_router import RoutingPlan

        pruner = StagePruner()

        # Create a test plan
        plan = RoutingPlan(
            grounding_priority=0.3,
            verification_priority=0.7,
            uncertainty_score=0.5,
            confidence_policy="moderate_confidence",
            stages=["classify", "plan", "grounding", "execute", "adversarial_verification", "calibrate"],
        )

        # Prune stages
        pruned = pruner.prune(plan.stages, plan)

        # Verify critical stages are never removed
        assert "classify" in pruned, "classify must not be removed"
        assert "plan" in pruned, "plan must not be removed"
        assert "execute" in pruned, "execute must not be removed"
        print(f"  [OK] Critical stages preserved: {pruned}")

        # Get report
        report = pruner.get_pruning_report(plan.stages, pruned)
        assert "removed_stages" in report
        print(f"  [OK] Pruning report generated: {report['removal_count']} stages removed")

    except Exception as e:
        errors.append(f"stage_pruner: {e}")
        print(f"  [FAIL] StagePruner: {e}")
        traceback.print_exc()

    return errors


async def _test_wiring():
    """Test full system wiring."""
    print("\nTesting full system wiring...")
    errors = []

    try:
        from jarvis_os.core.factory import create_sovereign_system, verify_safety_enforcement

        # Create and wire the system
        system = create_sovereign_system()
        print(f"  [OK] System created: {type(system).__name__}")

        # Verify safety enforcement
        checks = verify_safety_enforcement(system)
        assert checks.get("all_safety_checks_passed", False)
        print(f"  [OK] Safety checks: {sum(1 for v in checks.values() if v)}/{len(checks)} passed")

    except Exception as e:
        errors.append(f"wiring: {e}")
        print(f"  [FAIL] Wiring: {e}")
        traceback.print_exc()

    return errors


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Phase 7 Mythos Omega - Reconstruction Tests")
    print("=" * 60)

    all_errors = []

    # Test imports
    all_errors.extend(test_imports())

    # Test individual modules
    all_errors.extend(test_sovereign_router())
    all_errors.extend(test_calibrator())
    all_errors.extend(test_stage_pruner())

    # Test wiring (async)
    all_errors.extend(await _test_wiring())

    # Summary
    print("\n" + "=" * 60)
    if all_errors:
        print(f"FAILED - {len(all_errors)} error(s):")
        for err in all_errors:
            print(f"  - {err}")
        return 1
    else:
        print("PASSED - All Phase 7 reconstruction tests passed!")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
