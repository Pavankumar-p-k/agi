import asyncio
from pathlib import Path


ROOT = Path(__file__).resolve().parent

from gpu.pool import ModelPool
from core.model_router import model_for_role


DEFAULT_MODEL = model_for_role("chat")


async def run_chat() -> None:
    pool = ModelPool()
    await pool.warmup()

    messages = []
    print("JARVIS chat ready. Type /exit to quit.")
    while True:
        user_text = input("You: ").strip()
        if not user_text:
            continue
        if user_text.lower() in {"/exit", "/quit"}:
            break

        messages.append({"role": "user", "content": user_text})
        reply = await pool.chat(model=DEFAULT_MODEL, messages=messages)
        print(f"Jarvis: {reply}")
        messages.append({"role": "assistant", "content": reply})


def main() -> None:
    asyncio.run(run_chat())


if __name__ == "__main__":
    main()
