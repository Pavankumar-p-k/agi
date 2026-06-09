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

import os
import pytest

if os.environ.get("JARVIS_TEST_MODE"):
    pytest.skip("Skipping network e2e in test mode", allow_module_level=True)

import httpx, json

# Test the actual /p response in detail
r = httpx.post("http://localhost:8000/api/chat",
    json={"message": "/p introduce yourself in 3 slides"},
    timeout=180)
d = r.json()
print("=== FULL RESPONSE ===")
print(json.dumps(d, indent=2)[:3000])
print("=== SLIDES ===")
s = d.get("presentation", [])
print("Slides count:", len(s))
for i, x in enumerate(s):
    print(f"  {i+1}: view={x.get('view')} keys={list(x.keys())}")
