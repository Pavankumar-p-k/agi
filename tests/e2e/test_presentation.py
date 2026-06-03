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
