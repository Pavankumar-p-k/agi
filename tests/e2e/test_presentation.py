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

r = httpx.post("http://localhost:8000/api/chat",
    json={"message": "/p introduce yourself in 3 slides"},
    timeout=180)
d = r.json()
s = d.get("presentation", [])
print("Slides count:", len(s))
for i, x in enumerate(s[:6]):
    print(f"  {i+1}. view={x.get('view')} dur={x.get('duration')}ms fields={list(x.keys())}")
if len(s) == 0:
    print("Full response keys:", list(d.keys()))
    print("Response text:", d.get("response","")[:300])
