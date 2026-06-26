from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.providers.base import ExecutionProvider, ExecutionResult
from core.providers.memory import provider_memory

logger = logging.getLogger(__name__)


class BenchmarkCategory(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    KOTLIN = "kotlin"
    RUST = "rust"
    GO = "go"
    REACT = "react"
    ANDROID = "android"
    FASTAPI = "fastapi"
    SPRING = "spring"
    REFACTORING = "refactoring"
    DEBUGGING = "debugging"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    SECURITY = "security"
    ARCHITECTURE = "architecture"
    SCAFFOLD = "scaffold"


@dataclass
class BenchmarkTask:
    id: str
    category: BenchmarkCategory | str
    name: str
    prompt: str
    mode: str = "generate"
    language: str = ""
    framework: str = ""
    timeout: int = 120
    expected_artifact: str = ""

    def __post_init__(self):
        if isinstance(self.category, str):
            try:
                self.category = BenchmarkCategory(self.category)
            except ValueError:
                pass


@dataclass
class BenchmarkResult:
    task_id: str
    provider_id: str
    category: str
    language: str
    framework: str
    success: bool
    duration_ms: float
    quality_score: float = 0.0
    retries: int = 0
    crash: bool = False
    cost: float = 0.0
    tokens_used: int = 0
    exit_code: int = 0
    output_snippet: str = ""
    error: str = ""
    timestamp: float = 0.0


QUALITY_CHECKS: dict[str, list[str]] = {
    "python": ["def ", "class ", "import ", "return ", "print"],
    "javascript": ["function", "const ", "let ", "export", "import"],
    "typescript": ["interface", "type ", ": string", ": number", "function"],
    "java": ["public ", "class ", "void ", "String", "import "],
    "kotlin": ["fun ", "class ", "val ", "var ", "import "],
    "rust": ["fn ", "struct ", "impl ", "pub ", "let "],
    "go": ["func ", "package ", "import ", "type ", "return"],
    "react": ["function", "return (", "export", "import", "useState"],
    "android": ["Activity", "onCreate", "LayoutInflater", "findViewById", "@Override"],
    "fastapi": ["FastAPI", "app.", "@app.", "from fastapi", "import "],
    "spring": ["@RestController", "@Service", "@Autowired", "@GetMapping", "import "],
    "refactoring": ["def ", "class ", "function", "return"],
    "debugging": ["try:", "except", "if ", "print", "return"],
    "testing": ["def test_", "assert ", "class Test", "pytest", "unittest"],
    "documentation": ["\"\"\"", "'''", "Args:", "Returns:", "param"],
    "security": ["hash", "encrypt", "token", "validate", "sanitize"],
    "architecture": ["class ", "interface", "extends", "implements", "abstract"],
    "scaffold": ["def ", "class ", "import ", "from ", "return"],
}


def score_quality(output: str, category: str, language: str = "") -> float:
    if not output:
        return 0.0

    checks = []
    if language:
        lang_key = language.lower()
        if lang_key in QUALITY_CHECKS:
            checks.extend(QUALITY_CHECKS[lang_key])
    cat_key = category.lower() if isinstance(category, str) else category.value
    if cat_key in QUALITY_CHECKS:
        checks.extend(QUALITY_CHECKS[cat_key])

    if not checks:
        checks = ["def ", "class ", "function", "return", "import"]

    output_lower = output.lower()
    matches = sum(1 for c in checks if c.lower() in output_lower)
    raw = min(1.0, matches / max(len(checks), 1) * 2.0)

    length_bonus = min(0.15, len(output) / 10000 * 0.15)
    return min(1.0, raw + length_bonus)


TASKS: list[BenchmarkTask] = [
    BenchmarkTask("py_crud_api", "python", "Python CRUD API", 
        "Write a FastAPI CRUD API for a todo list with create, read, update, delete endpoints using an in-memory store.", 
        language="python", framework="fastapi"),
    BenchmarkTask("py_sort_algo", "python", "Python Sorting Algorithm", 
        "Write a Python function that implements merge sort with type hints and a test example.", 
        language="python"),
    BenchmarkTask("py_data_class", "python", "Python Dataclass Model", 
        "Create a Python dataclass for a User with id, name, email, created_at fields. Include a method to validate email format.", 
        language="python"),
    BenchmarkTask("js_array_utils", "javascript", "JavaScript Array Utilities", 
        "Write JavaScript utility functions: deepClone, groupBy, flatten, unique. Use modern JS (ES6+).", 
        language="javascript"),
    BenchmarkTask("js_promise_all", "javascript", "JavaScript Async Helpers", 
        "Write JavaScript async utility: promiseAllSettledMap that runs async functions with a concurrency limit.", 
        language="javascript"),
    BenchmarkTask("ts_generic_utils", "typescript", "TypeScript Generic Utilities", 
        "Write TypeScript generic utility types: DeepPartial, Nullable, PickByType, and a function that uses them.", 
        language="typescript"),
    BenchmarkTask("ts_api_client", "typescript", "TypeScript API Client", 
        "Write a TypeScript API client class with generic request method, typed responses, and error handling.", 
        language="typescript"),
    BenchmarkTask("java_class_model", "java", "Java Class Model", 
        "Write a Java class for a Book with id, title, author, isbn, year. Include getters, setters, equals, hashCode, toString.", 
        language="java"),
    BenchmarkTask("java_stream_example", "java", "Java Stream Processing", 
        "Write a Java method that uses streams to filter, map, and collect a list of Employee objects. Include the Employee class.", 
        language="java"),
    BenchmarkTask("kt_data_class", "kotlin", "Kotlin Data Class", 
        "Write a Kotlin data class for a Product with id, name, price, category. Include extension functions for discount and tax.", 
        language="kotlin"),
    BenchmarkTask("kt_coroutine_example", "kotlin", "Kotlin Coroutine Example", 
        "Write a Kotlin class that uses coroutines to fetch data from multiple APIs concurrently and combine results.", 
        language="kotlin"),
    BenchmarkTask("rs_cli_tool", "rust", "Rust CLI Tool", 
        "Write a Rust command-line tool that reads a CSV file, filters rows by a column value, and prints the result.", 
        language="rust"),
    BenchmarkTask("rs_error_handling", "rust", "Rust Error Handling", 
        "Write a Rust module that demonstrates idiomatic error handling with custom error types, From impls, and ? operator.", 
        language="rust"),
    BenchmarkTask("go_http_server", "go", "Go HTTP Server", 
        "Write a Go HTTP server with health endpoint, JSON response middleware, and graceful shutdown.", 
        language="go"),
    BenchmarkTask("go_concurrent_worker", "go", "Go Concurrent Worker", 
        "Write a Go worker pool that processes jobs concurrently using goroutines and channels.", 
        language="go"),
    BenchmarkTask("react_todo_component", "react", "React Todo Component", 
        "Write a React functional component for a todo list with add, toggle, delete, and filter (all/active/completed). Use hooks.", 
        language="typescript", framework="react"),
    BenchmarkTask("react_custom_hook", "react", "React Custom Hook", 
        "Write a React custom hook useLocalStorage that syncs state with localStorage, including SSR safety.", 
        language="typescript", framework="react"),
    BenchmarkTask("android_activity", "android", "Android Activity", 
        "Write an Android Activity that displays a RecyclerView with user list loaded from a ViewModel + Repository pattern.", 
        language="kotlin", framework="android"),
    BenchmarkTask("android_room_dao", "android", "Android Room DAO", 
        "Write an Android Room DAO interface for a Note entity with insert, update, delete, and search queries.", 
        language="kotlin", framework="android"),
    BenchmarkTask("fastapi_auth", "fastapi", "FastAPI Auth Endpoint", 
        "Write a FastAPI app with user registration, login, JWT token generation, and a protected profile endpoint.", 
        language="python", framework="fastapi"),
    BenchmarkTask("fastapi_websocket", "fastapi", "FastAPI WebSocket", 
        "Write a FastAPI WebSocket endpoint that echoes messages and broadcasts to connected clients.", 
        language="python", framework="fastapi"),
    BenchmarkTask("spring_rest", "spring", "Spring REST Controller", 
        "Write a Spring Boot REST controller for a Product entity with CRUD operations, validation, and exception handling.", 
        language="java", framework="spring"),
    BenchmarkTask("spring_service", "spring", "Spring Service Layer", 
        "Write a Spring Boot service class with @Transactional methods for an Order processing workflow.", 
        language="java", framework="spring"),
    BenchmarkTask("refactor_smelly", BenchmarkCategory.REFACTORING, "Refactor Smelly Code", 
        """Refactor this code. It works but has many issues: long method, magic numbers, nested conditionals, unused params.
        def calc(a, b, c, d):
            if a > 10:
                if b < 5:
                    return a * b + 42
                elif c == 0:
                    return a * 2 + 42
                else:
                    return a + b + c + 42
            elif a > 5:
                return a * 3 + 42
            else:
                return 42
        """, mode="refactor", language="python"),
    BenchmarkTask("debug_npe", BenchmarkCategory.DEBUGGING, "Debug Null Pointer", 
        """Fix the bug. This code crashes with 'NoneType' object has no attribute 'get'.
        users = {"alice": {"email": "alice@example.com", "age": 30}}
        def get_email(name):
            user = users.get(name)
            return user.get("email")
        print(get_email("bob"))
        """, mode="debug", language="python"),
    BenchmarkTask("test_pytest", BenchmarkCategory.TESTING, "Write Pytest Tests", 
        "Write pytest tests for a function that validates email addresses. Include tests for valid, invalid, edge cases, and parametrized tests.",
        mode="test", language="python"),
    BenchmarkTask("test_jest", BenchmarkCategory.TESTING, "Write Jest Tests", 
        "Write Jest tests for a debounce function. Include tests for timing, leading edge, trailing edge, and cancel.",
        mode="test", language="javascript"),
    BenchmarkTask("docs_api_endpoint", BenchmarkCategory.DOCUMENTATION, "Document API Endpoint", 
        "Write comprehensive documentation for a REST API endpoint that creates an order. Include request/response schemas, error codes, and examples.",
        mode="document", language="python"),
    BenchmarkTask("security_sql_injection", BenchmarkCategory.SECURITY, "Fix SQL Injection", 
        """Fix the security vulnerability. This code is vulnerable to SQL injection.
        def get_user(username):
            query = f"SELECT * FROM users WHERE username = '{username}'"
            cursor.execute(query)
            return cursor.fetchone()
        """, mode="fix", language="python"),
    BenchmarkTask("arch_design_pattern", BenchmarkCategory.ARCHITECTURE, "Design Pattern Implementation", 
        "Implement the Strategy pattern in Python for a payment processing system that supports credit card, PayPal, and crypto payments.",
        mode="generate", language="python"),
    BenchmarkTask("scaffold_cli", BenchmarkCategory.SCAFFOLD, "Scaffold CLI Tool", 
        "Write a Python CLI tool using argparse or click that reads a JSON config file, validates it, and prints a summary.",
        mode="generate", language="python"),
]


def get_tasks(category: str | None = None, language: str | None = None) -> list[BenchmarkTask]:
    result = list(TASKS)
    if category:
        cat = category.lower()
        result = [t for t in result if (isinstance(t.category, str) and t.category.lower() == cat) or (hasattr(t.category, 'value') and t.category.value == cat)]
    if language:
        lang = language.lower()
        result = [t for t in result if t.language.lower() == lang]
    return result


def get_categories() -> list[str]:
    seen: set[str] = set()
    cats: list[str] = []
    for t in TASKS:
        cat = t.category.value if isinstance(t.category, Enum) else str(t.category)
        if cat not in seen:
            seen.add(cat)
            cats.append(cat)
    return cats


class BenchmarkRunner:
    def __init__(self, store=None):
        self._store = store
        from core.providers.benchmark_store import BenchmarkStore
        self._store = store or BenchmarkStore()

    async def run_task(self, task: BenchmarkTask, provider: ExecutionProvider) -> BenchmarkResult:
        start = time.monotonic()
        retries = 0
        crash = False
        error = ""

        result: ExecutionResult | None = None
        try:
            result = await provider.execute({
                "goal": task.prompt,
                "mode": task.mode,
                "timeout": task.timeout,
            })
        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            return BenchmarkResult(
                task_id=task.id, provider_id=provider.provider_id,
                category=task.category.value if isinstance(task.category, Enum) else str(task.category),
                language=task.language, framework=task.framework,
                success=False, duration_ms=elapsed, error="timeout",
                timestamp=time.time(),
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return BenchmarkResult(
                task_id=task.id, provider_id=provider.provider_id,
                category=task.category.value if isinstance(task.category, Enum) else str(task.category),
                language=task.language, framework=task.framework,
                success=False, duration_ms=elapsed, crash=True, error=str(e)[:200],
                timestamp=time.time(),
            )

        elapsed = (time.monotonic() - start) * 1000
        output = result.output if result else ""
        quality = score_quality(output, task.category, task.language)

        return BenchmarkResult(
            task_id=task.id, provider_id=provider.provider_id,
            category=task.category.value if isinstance(task.category, Enum) else str(task.category),
            language=task.language, framework=task.framework,
            success=result.success if result else False,
            duration_ms=elapsed, quality_score=quality,
            retries=retries, crash=crash,
            cost=0.0, tokens_used=0,
            exit_code=result.exit_code if result else 1,
            output_snippet=output[:500], error=error,
            timestamp=time.time(),
        )

    async def run_provider(self, provider: ExecutionProvider, category: str | None = None) -> list[BenchmarkResult]:
        tasks = get_tasks(category=category)
        results: list[BenchmarkResult] = []
        for task in tasks:
            br = await self.run_task(task, provider)
            results.append(br)
        self._store.save_results(results)
        for br in results:
            provider_memory.record_execution(
                provider_id=br.provider_id,
                success=br.success,
                duration_ms=br.duration_ms,
                capability=br.category,
                language=br.language,
                framework=br.framework,
                tokens_used=br.tokens_used,
                cost=br.cost,
            )
        return results

    async def run_all(self, providers: list[ExecutionProvider], category: str | None = None) -> dict[str, list[BenchmarkResult]]:
        all_results: dict[str, list[BenchmarkResult]] = {}
        for provider in providers:
            results = await self.run_provider(provider, category)
            all_results[provider.provider_id] = results
        return all_results
