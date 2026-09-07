import requests
from bs4 import BeautifulSoup
import time


def fetch_webpage_content(url: str, timeout: int = 10) -> dict:
    """Fetch a web page's textual content and title.

    Strategy:
    - Attempt a simple requests.get and parse HTML with BeautifulSoup.
    - If content-type isn't HTML or the body is nearly empty, attempt to use Playwright
      (if available) to render JS-heavy pages.

    Returns dict with keys: content (text), title, error (optional)
    """
    result = {"content": "", "title": "", "error": None}
    try:
        headers = {"User-Agent": "JARVIS/1.0 (+https://example.local)"}
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        ctype = r.headers.get("Content-Type", "").lower()
        text = r.text or ""
        if "html" in ctype and len(text.strip()) > 100:
            soup = BeautifulSoup(text, "html.parser")
            title = soup.title.string.strip() if soup.title and soup.title.string else ""
            # extract visible text from <body>
            body = soup.body
            if body:
                # get text and normalize whitespace
                content = "\n\n".join([p.get_text(separator=" ", strip=True) for p in body.find_all(["p", "li"])])
                if not content:
                    content = soup.get_text(separator=" ", strip=True)
            else:
                content = soup.get_text(separator=" ", strip=True)
            result["content"] = content
            result["title"] = title
            return result

        # Fallback: try Playwright render for JS-heavy pages
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            result["error"] = f"requests fetched non-HTML or short content and Playwright unavailable: {e}"
            return result

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=timeout * 1000)
                time.sleep(0.5)
                title = page.title() or ""
                # grab visible text
                content = page.content()
                soup = BeautifulSoup(content, "html.parser")
                body = soup.body
                if body:
                    content_text = "\n\n".join([p.get_text(separator=" ", strip=True) for p in body.find_all(["p", "li"])])
                    if not content_text:
                        content_text = soup.get_text(separator=" ", strip=True)
                else:
                    content_text = soup.get_text(separator=" ", strip=True)
                result["content"] = content_text
                result["title"] = title
                try:
                    browser.close()
                except Exception:
                    pass
                return result
        except Exception as e:
            result["error"] = f"Playwright render failed: {e}"
            return result

    except Exception as e:
        result["error"] = str(e)
        return result
