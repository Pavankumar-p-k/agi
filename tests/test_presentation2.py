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
