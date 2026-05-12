import asyncio
from assistant.engine import jarvis

async def test_llm():
    print("Testing LLM availability...")
    available = await jarvis.llm.is_available()
    print(f"LLM available: {available}")

    if available:
        print("Testing intent extraction...")
        intent = await jarvis.llm.extract_intent("open notepad")
        print(f"Extracted intent: {intent}")

        print("Testing chat...")
        response = await jarvis.llm.chat("hello jarvis")
        print(f"Chat response: {response}")
    else:
        print("Skipping LLM tests as Ollama is not reachable.")

if __name__ == "__main__":
    asyncio.run(test_llm())
