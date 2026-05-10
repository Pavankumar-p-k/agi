import os
from jarvis_os.runtime.config import JarvisConfig
from jarvis_os.RuntimeGovernanceLayer import RuntimeGovernanceLayer
from jarvis_os.ProviderDecisionMatrix import ProviderDecisionMatrix
from jarvis_os.ProviderTrustRegistry import ProviderTrustRegistry
from jarvis_os.ProviderStrategicMemory import ProviderStrategicMemory

# Enable network so that rest is theoretically available
os.environ["JARVIS_ALLOW_NETWORK"] = "1"

config = JarvisConfig.from_env()

trust = ProviderTrustRegistry({"rest": None, "ollama": None})
strategic = ProviderStrategicMemory(config)
decision = ProviderDecisionMatrix(config, trust, strategic)

layer = RuntimeGovernanceLayer(
    trust,
    None,
    decision,
    strategic,
    config
)

task = {"action": "check bank statement for user transactions", "content": "financial data here"}
task_normal = {"action": "write a python script"}
task_medical = {"action": "analyze my medical record for allergies"}

candidates = {"rest": {"provider": "rest", "ready": True, "privacy": 0.5, "trustworthiness": 1.0}, "ollama": {"provider": "ollama", "ready": True, "offline_availability": 1.0, "privacy": 1.0, "trustworthiness": 1.0}}

print("--- Test 1: Financial ---")
try:
    selection = layer.finalize_selection(candidates, task["action"])
    if selection["provider"] == "rest":
        print("FAIL. Rest was allowed for financial task!")
    else:
        print("PASS. Rest blocked. Selected:", selection["provider"])
except Exception as e:
    print("PASS. Blocked:", e)

print("--- Test 2: Normal ---")
try:
    selection2 = layer.finalize_selection(candidates, task_normal["action"])
    if selection2["provider"] == "rest":
        print("PASS. Rest allowed for normal task.")
    else:
        print("FAIL. Rest was not selected for normal task.")
except Exception as e:
    print("FAIL. Exception:", e)

print("--- Test 3: Medical ---")
try:
    selection3 = layer.finalize_selection(candidates, task_medical["action"])
    if selection3["provider"] == "rest":
        print("FAIL. Rest was allowed for medical task!")
    else:
        print("PASS. Rest blocked. Selected:", selection3["provider"])
except Exception as e:
    print("PASS. Blocked:", e)
