import sys; sys.path.insert(0, '.')
import asyncio
import urllib.request
from skills.library.entertainment.spotify.main import spotify

async def test():
    print('=== Testing REAL audio playback ===')
    print()

    r = await spotify({'action': 'play', 'song': 'relaxing piano music'})
    s = r['status']
    d = r.get('data', {})
    print(f'1. Melody playback: {s}')
    print(f'   Audio: {d.get("audio", "none")}')
    print(f'   Method: {d.get("method", "none")}')
    print()

    r = await spotify({'action': 'beep'})
    print(f'2. Beep test: {r["status"]} | played={r.get("data",{}).get("played", False)}')
    print()

    print('3. Live website at http://localhost:8080')
    try:
        with urllib.request.urlopen('http://127.0.0.1:8080/', timeout=3) as resp:
            html = resp.read().decode()
            print(f'   Server: HTTP {resp.status}')
            print(f'   index.html: {len(html)} bytes loaded')
    except Exception as e:
        print(f'   Server: {e}')

asyncio.run(test())
