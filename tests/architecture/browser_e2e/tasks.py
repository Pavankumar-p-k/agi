"""100 end-to-end browser benchmark task definitions with outcome-based validation."""


class BrowserTask:
    def __init__(self, prompt, category, *,
                 min_tool_calls=1, verify_substring=None, timeout=120,
                 needs_navigate=True, needs_search=False, needs_snapshot=False,
                 needs_click=False, needs_fill=False):
        self.prompt = prompt
        self.category = category
        self.min_tool_calls = min_tool_calls
        self.verify_substring = verify_substring
        self.timeout = timeout
        self.needs_navigate = needs_navigate
        self.needs_search = needs_search
        self.needs_snapshot = needs_snapshot
        self.needs_click = needs_click
        self.needs_fill = needs_fill

    def check_success(self, tool_calls, agent_response):
        called = {tc.get("name", "") for tc in tool_calls}

        if len(tool_calls) < self.min_tool_calls:
            return False, "too_few_calls:{}<{}".format(len(tool_calls), self.min_tool_calls)

        # Check for actual tool errors, not the word "error" in narrative text.
        # The LLM often says "I tried to search but got an error" even when
        # tools succeeded — so we validate based on tool results instead.
        tool_errors = [tc for tc in tool_calls if tc.get("result", {}).get("status") == "error"]
        if tool_errors:
            return False, "error_in_response"

        if self.needs_navigate and "browser_navigate" not in called:
            return False, "missing_navigate"

        # Search check: accept browser_find OR (evaluate+fill+press) OR (fill+press)
        # to handle both the old find-based and new planner-based approach.
        if self.needs_search:
            has_find = "browser_find" in called
            has_fill_press = "browser_fill" in called and "browser_press" in called
            if not (has_find or has_fill_press):
                return False, "missing_search"

        if self.needs_snapshot and "browser_snapshot" not in called:
            return False, "missing_snapshot"

        # Click check: accept browser_click OR planner-driven click (evaluate
        # returning a URL -> navigate, or multiple navigations). Multi-page
        # tasks use the planner's result-click rule instead of LLM-generated
        # browser_click. Tool_start events don't carry results, so we detect
        # planner-driven clicks by counting navigate calls (2+ navigations
        # means the planner navigated to a search result or page link).
        if self.needs_click:
            has_click = "browser_click" in called
            if not has_click:
                navigate_count = sum(1 for tc in tool_calls if tc.get("name") == "browser_navigate")
                has_click = navigate_count >= 2
            if not has_click:
                return False, "missing_click"

        if self.needs_fill and "browser_fill" not in called:
            return False, "missing_fill"

        if self.verify_substring and agent_response:
            if self.verify_substring.lower() not in agent_response.lower():
                return False, "missing_verification:" + self.verify_substring

        return True, ""


# ── Task generators ──────────────────────────────────────────────

def _tasks_search():
    return [
        BrowserTask("Search Google for 'Python requests library' and read the first result.", "Search workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, verify_substring="requests"),
        BrowserTask("Search DuckDuckGo for 'FastAPI tutorial' and summarize the first result.", "Search workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, verify_substring="FastAPI"),
        BrowserTask("Go to Wikipedia and search for 'Artificial Intelligence'.", "Search workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, verify_substring="intelligence"),
        BrowserTask("Search Google for 'Python asyncio vs threading' comparison.", "Search workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True),
        BrowserTask("Open Bing and search for 'best IDE for Python development'.", "Search workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, verify_substring="Python"),
        BrowserTask("Open YouTube and search for 'Python machine learning tutorial'.", "Search workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True),
        BrowserTask("Go to PyPI and search for the 'requests' package.", "Search workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, verify_substring="requests"),
        BrowserTask("Open GitHub and search for 'fastapi' repositories.", "Search workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, verify_substring="fastapi"),
        BrowserTask("Search Stack Overflow for 'python async await example'.", "Search workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, verify_substring="async"),
        BrowserTask("Open the Python Package Index and search for 'numpy'.", "Search workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, verify_substring="numpy"),
    ]


def _tasks_documentation():
    return [
        BrowserTask("Open Python docs on asyncio and read the overview.", "Documentation workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="asyncio"),
        BrowserTask("Open the FastAPI docs and find the 'First Steps' section.", "Documentation workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="FastAPI"),
        BrowserTask("Browse Django docs and find the model relationship guide.", "Documentation workflows",
                    needs_navigate=True, needs_snapshot=True),
        BrowserTask("Open React docs page for the useState hook.", "Documentation workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="useState"),
        BrowserTask("Open Docker docs and find Compose file reference.", "Documentation workflows",
                    needs_navigate=True, needs_snapshot=True),
        BrowserTask("Open PyTorch docs on tensor operations.", "Documentation workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="tensor"),
        BrowserTask("Open Playwright docs for locators.", "Documentation workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="locator"),
        BrowserTask("Browse FastAPI docs for dependency injection examples.", "Documentation workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="dependency"),
        BrowserTask("Open Flask docs for the quickstart guide.", "Documentation workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="quickstart"),
        BrowserTask("Open NumPy docs for array creation examples.", "Documentation workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="array"),
    ]


def _tasks_github():
    return [
        BrowserTask("Open the FastAPI GitHub repo and read the README.", "GitHub workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="FastAPI"),
        BrowserTask("Open python/cpython repo and check open issues.", "GitHub workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="issue"),
        BrowserTask("Browse pandas-dev/pandas repo and find the contributing guide.", "GitHub workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="contributing"),
        BrowserTask("Open encode/httpx repo and check the latest release.", "GitHub workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="release"),
        BrowserTask("Browse tiangolo/fastapi repo and look at pull requests.", "GitHub workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="pull"),
        BrowserTask("Open microsoft/vscode repo and find README build badges.", "GitHub workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="VS Code"),
        BrowserTask("Browse pallets/flask repo and check the license.", "GitHub workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="license"),
        BrowserTask("Open psf/requests repo and find installation instructions.", "GitHub workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="pip install"),
        BrowserTask("Browse django/django repo for open issues labeled 'bug'.", "GitHub workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="bug"),
        BrowserTask("Open nod-ai/SHAQ repo and check its description.", "GitHub workflows",
                    needs_navigate=True, needs_snapshot=True),
    ]


def _tasks_research():
    return [
        BrowserTask("Read the official Python 3.13 release doc and find new features.", "Research workflows",
                    needs_navigate=True, needs_snapshot=True, min_tool_calls=2, verify_substring="Python"),
        BrowserTask("Research SQL vs NoSQL databases by reading a comparison.", "Research workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Research what MLOps is and find three key practices.", "Research workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Read the Wikipedia article on Linux and summarize its history.", "Research workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="Linux"),
        BrowserTask("Research pros and cons of microservices vs monolith.", "Research workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Research environmental impact of crypto mining.", "Research workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Research the best Python web frameworks in 2026.", "Research workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Read the MDN docs on WebAssembly and explain its uses.", "Research workflows",
                    needs_navigate=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Read the Wikipedia article on quantum computing.", "Research workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="quantum"),
        BrowserTask("Research software engineer salary ranges.", "Research workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2),
    ]


def _tasks_shopping():
    return [
        BrowserTask("Search Amazon for 'wireless mouse' and read features.", "Shopping workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Browse eBay for used ThinkPad laptops under $300.", "Shopping workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Search Amazon for USB-C hub and read product details.", "Shopping workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Browse Best Buy for 27-inch 4K monitors.", "Shopping workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True),
        BrowserTask("Search Walmart for office chairs under $200.", "Shopping workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True),
        BrowserTask("Browse Etsy for handmade leather wallets.", "Shopping workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True),
        BrowserTask("Search AliExpress for Arduino starter kit.", "Shopping workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True),
        BrowserTask("Search Amazon for 'mechanical keyboard' and compare.", "Shopping workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Browse Newegg for gaming laptops.", "Shopping workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True),
        BrowserTask("Search Amazon for 'Python programming book' bestseller.", "Shopping workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True),
    ]


def _tasks_learning():
    return [
        BrowserTask("Find a Python tutorial on Real Python and read the first lesson.", "Learning workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Open W3Schools SQL tutorial and read about SELECT.", "Learning workflows",
                    needs_navigate=True, needs_snapshot=True, verify_substring="SELECT"),
        BrowserTask("Find a freeCodeCamp tutorial on JavaScript promises.", "Learning workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Open a DigitalOcean tutorial on Docker.", "Learning workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Find a Git branching tutorial on Atlassian.", "Learning workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True),
        BrowserTask("Find a free ML course on Coursera or edX.", "Learning workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True),
        BrowserTask("Find a tutorial on building REST APIs with FastAPI.", "Learning workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Open a GraphQL tutorial on Apollo docs.", "Learning workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True),
        BrowserTask("Find a CI/CD pipeline tutorial with GitHub Actions.", "Learning workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True),
        BrowserTask("Open a Kubernetes tutorial on K8s official docs.", "Learning workflows",
                    needs_navigate=True, needs_snapshot=True, min_tool_calls=2),
    ]


def _tasks_form():
    return [
        BrowserTask("Go to Google and search for 'Python 3.13 release notes'.", "Form workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, verify_substring="Python"),
        BrowserTask("Open GitHub and search for 'opencode' repositories.", "Form workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, verify_substring="opencode"),
        BrowserTask("Go to Wikipedia and search for 'Transformer architecture'.", "Form workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, verify_substring="Transformer"),
        BrowserTask("Open YouTube and search for 'async Python tutorial'.", "Form workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, verify_substring="Python"),
        BrowserTask("Open Stack Overflow and search for 'python decorator'.", "Form workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True),
        BrowserTask("Open Reddit and search for 'learn machine learning'.", "Form workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True),
        BrowserTask("Go to Medium and search for 'Python best practices 2026'.", "Form workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, verify_substring="Python"),
        BrowserTask("Open npm and search for 'typescript' packages.", "Form workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, verify_substring="typescript"),
        BrowserTask("Go to GitHub and search for 'browser automation' projects.", "Form workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True),
        BrowserTask("Open Twitter and search for 'AI news' trending topics.", "Form workflows",
                    needs_navigate=True, needs_search=True, needs_snapshot=True),
    ]


def _tasks_multipage():
    return [
        BrowserTask("Open Google, search for 'Python async', and open the first result.", "Multi-page navigation",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, needs_click=True, min_tool_calls=3),
        BrowserTask("Open a Wikipedia article on Python and find a reference link.", "Multi-page navigation",
                    needs_navigate=True, needs_search=True, needs_click=True, needs_snapshot=True, min_tool_calls=3),
        BrowserTask("Open GitHub, search for 'fastapi', open the first repo.", "Multi-page navigation",
                    needs_navigate=True, needs_search=True, needs_click=True, needs_snapshot=True, min_tool_calls=3),
        BrowserTask("Open Amazon, search for 'monitor', click first product.", "Multi-page navigation",
                    needs_navigate=True, needs_search=True, needs_click=True, needs_snapshot=True, min_tool_calls=3),
        BrowserTask("Open Reddit, go to r/Python, open top post.", "Multi-page navigation",
                    needs_navigate=True, needs_snapshot=True, needs_click=True, min_tool_calls=3),
        BrowserTask("Open Stack Overflow, search a question, open the answer.", "Multi-page navigation",
                    needs_navigate=True, needs_search=True, needs_click=True, needs_snapshot=True, min_tool_calls=3),
        BrowserTask("Open YouTube, search a tutorial, open the first video.", "Multi-page navigation",
                    needs_navigate=True, needs_search=True, needs_click=True, needs_snapshot=True, min_tool_calls=3),
        BrowserTask("Open a blog post, read it, and open a related link.", "Multi-page navigation",
                    needs_navigate=True, needs_click=True, needs_snapshot=True, min_tool_calls=3),
        BrowserTask("Open GitHub trending page, click first Python repo.", "Multi-page navigation",
                    needs_navigate=True, needs_click=True, needs_snapshot=True, min_tool_calls=3),
        BrowserTask("Open PyPI, search for a library, open its page.", "Multi-page navigation",
                    needs_navigate=True, needs_search=True, needs_click=True, needs_snapshot=True, min_tool_calls=3),
    ]


def _tasks_extraction():
    return [
        BrowserTask("Extract the title and main topic of a Wikipedia page on Python.", "Information extraction",
                    needs_navigate=True, needs_snapshot=True, verify_substring="Python"),
        BrowserTask("Find and extract the install command from the pip documentation.", "Information extraction",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2, verify_substring="pip"),
        BrowserTask("Extract the current price of a product on Amazon.", "Information extraction",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Find the star count of the FastAPI GitHub repository.", "Information extraction",
                    needs_navigate=True, needs_snapshot=True, verify_substring="star"),
        BrowserTask("Extract the first code example from the Python requests docs.", "Information extraction",
                    needs_navigate=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Find the latest Python version on the Python downloads page.", "Information extraction",
                    needs_navigate=True, needs_snapshot=True, min_tool_calls=2, verify_substring="Python"),
        BrowserTask("Read the Python docs definition of 'asyncio'.", "Information extraction",
                    needs_navigate=True, needs_snapshot=True, min_tool_calls=2, verify_substring="asyncio"),
        BrowserTask("Find the license type of the Flask web framework.", "Information extraction",
                    needs_navigate=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Extract the key features of the Rust programming language.", "Information extraction",
                    needs_navigate=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Find the top 3 most popular Python packages on PyPI.", "Information extraction",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2),
    ]


def _tasks_recovery():
    return [
        BrowserTask("Navigate to an invalid URL and recover by searching instead.", "Recovery/error handling",
                    needs_search=True, min_tool_calls=2),
        BrowserTask("Click a non-existent element and handle the error gracefully.", "Recovery/error handling",
                    needs_navigate=True, needs_click=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Navigate to a slow page and handle the timeout.", "Recovery/error handling",
                    needs_navigate=True, needs_snapshot=True),
        BrowserTask("Open a page with no interactive elements and adapt.", "Recovery/error handling",
                    needs_navigate=True, needs_snapshot=True),
        BrowserTask("Try to fill a disabled form field and handle the failure.", "Recovery/error handling",
                    needs_navigate=True, needs_fill=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Navigate to a blocked site and fall back to an alternative.", "Recovery/error handling",
                    needs_navigate=True, needs_search=True, min_tool_calls=2),
        BrowserTask("Open a page with broken JavaScript and still extract content.", "Recovery/error handling",
                    needs_navigate=True, needs_snapshot=True),
        BrowserTask("Search for an obscure term and still provide a useful answer.", "Recovery/error handling",
                    needs_navigate=True, needs_search=True, needs_snapshot=True, min_tool_calls=2),
        BrowserTask("Try opening a PDF URL and fall back to the HTML version.", "Recovery/error handling",
                    needs_navigate=True, needs_search=True),
        BrowserTask("Navigate to a 404 page and navigate back to search.", "Recovery/error handling",
                    needs_navigate=True, needs_search=True, min_tool_calls=2),
    ]


def get_all_tasks():
    tasks = []
    tasks.extend(_tasks_search())
    tasks.extend(_tasks_documentation())
    tasks.extend(_tasks_github())
    tasks.extend(_tasks_research())
    tasks.extend(_tasks_shopping())
    tasks.extend(_tasks_learning())
    tasks.extend(_tasks_form())
    tasks.extend(_tasks_multipage())
    tasks.extend(_tasks_extraction())
    tasks.extend(_tasks_recovery())
    return tasks
