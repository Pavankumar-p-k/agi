# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
