"""Test Crawl4AI scraping."""
import asyncio
import sys
sys.stdout = open(sys.stdout.fileno(), 'w', encoding='utf-8', errors='replace')

from tools.crawl4ai_tool import get_crawler


async def main():
    c = get_crawler()
    r = await c.scrape("https://example.com")
    print(f"Success: {r['success']}")
    print(f"Content length: {len(r.get('content', ''))}")
    print(f"Title: {r.get('title', '')}")
    await c.close()


if __name__ == "__main__":
    asyncio.run(main())
