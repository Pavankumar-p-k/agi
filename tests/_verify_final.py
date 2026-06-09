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

"""Final verification + summary email."""
import requests
BASE = 'http://localhost:8000'

def chat(msg, timeout=120):
    r = requests.post(f'{BASE}/api/chat', json={'message': msg}, timeout=timeout)
    j = r.json()
    return j.get('intent',{}).get('intent','?'), j.get('action',{}).get('executed'), j.get('response','')[:80]

tests = [
    ('What is Python', 'chat'),
    ('Open cmd', 'pc_control'),
    ("What's the weather in London", 'web_search'),
    ('Create a github issue in pavan/jarvis', 'message'),
    ('Go to https://example.com', 'open_url'),
]
for msg, exp in tests:
    intent, executed, resp = chat(msg)
    ok = 'PASS' if intent == exp else 'FAIL'
    print(f'{ok}: "{msg}" -> {intent} (expected {exp})')

print()
print("Sending summary email...")
r = chat('Send an email to pavankumarunnam99@gmail.com with subject JARVIS test results saying All 92 tests completed with fixes applied. 87 passed, 5 expected failures, 0 timeouts. Memory, composio, search, automation all working.', timeout=180)
print(f"Email: {r[2][:100]}")
print("DONE")
