"""Test LiteLLM call directly to see what format it returns."""
import asyncio, sys, os
sys.path.insert(0, os.getcwd())
from core.llm_router import get_router
llm_router = get_router()

async def test():
    slide_prompt = 'Output ONLY a valid JSON array. Generate 3 slides for topic: introduce yourself. [{"view":"card","type":"creator","image":"pavan.jpg","title":"HI","text":"hello","duration":5000}]'
    try:
        reply = await llm_router.acompletion(
            model="automation",
            messages=[
                {"role": "system", "content": "Output ONLY JSON."},
                {"role": "user", "content": slide_prompt}
            ],
            timeout=60
        )
        raw = reply.choices[0].message.content
        print("=== RAW LITELLM ===")
        print(repr(raw[:1000]))
    except Exception as e:
        print(f"ERROR: {e}")

asyncio.run(test())
