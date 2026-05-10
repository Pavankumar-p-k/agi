import asyncio
import logging
logging.basicConfig(level=logging.DEBUG)
from brain.MetaCognitionEngine import ExecutiveMetaCognitionV3
from brain.ContinuousCognitionLoop import ContinuousCognitionLoopV3

async def test_self_repair():
    print("--- Testing MetaCognition Self-Audit ---")
    engine = ExecutiveMetaCognitionV3()
    result = engine.self_audit()
    print("Self-Audit Output:")
    for key, value in result.items():
        print(f"  {key}: {value}")

    print("\n--- Testing Continuous Cognition Tick Methods ---")
    loop = ContinuousCognitionLoopV3()
    await loop._execute_health_checks()
    await loop._execute_benchmark_reruns()
    await loop._execute_drift_scans()
    await loop._execute_provider_audits()
    loop._execute_governance_penetration_test()
    await loop._generate_strategic_evolution_report()
    print("Manual cognition cycle completed.")

if __name__ == "__main__":
    asyncio.run(test_self_repair())
