import asyncio
import json
from assistant.engine import jarvis
from assistant.smart_actions import execute_action

async def test_full_pipeline():
    print("Testing Full Pipeline (Mocked Action execution)...")

    # Mocking Ollama response for testing without a running server
    # In a real environment, we'd check if jarvis.llm.is_available()

    test_message = "remind me to buy milk in 2 hours"
    print(f"User: {test_message}")

    # Simulating what process_text does
    # 1. Intent extraction (would normally call LLM)
    # We'll just test the execute_action part since we verified time parsing

    intent_data = {"action": "set_reminder", "title": "buy milk", "time": "in 2 hours"}
    print(f"Simulated Intent: {intent_data}")

    # We need to mock the API call in execute_action or ensure server is running
    # For this test, we'll just check if it correctly routes and handles params

    try:
        # This will likely fail to connect to localhost:8000 but we want to see it try
        result = await execute_action(intent_data)
        print(f"Action Result: {result}")
    except Exception as e:
        print(f"Action failed as expected (no server): {e}")

    # Test PC control routing
    pc_intent = {"action": "pc_control", "app": "notepad"}
    print(f"Simulated PC Intent: {pc_intent}")
    # result = await execute_action(pc_intent) # This would open notepad on a real machine
    # print(f"PC Action Result: {result}")

if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
