import sys, asyncio
sys.path.insert(0, ".")
from core.tools.browser_tools import do_browser_navigate
async def main():
    out = await do_browser_navigate("http://example.com")
    print("status:", out.get("status"), "|", str(out.get("error"))[:120])
asyncio.run(main())
