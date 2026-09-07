"""Metrics collection for the browser E2E benchmark."""
from collections import Counter, defaultdict


class Metrics:
    def __init__(self):
        self.tasks = []
        self.tool_usage = Counter()
        self.tool_errors = Counter()
        self.failure_reasons = Counter()
        self.category_results = defaultdict(lambda: {"pass": 0, "fail": 0, "total": 0})
        self.state_leak_count = 0
        self.cross_task_nav_count = 0

    def record_task(self, idx, task, passed, reason, tool_calls, latency, agent_response, metadata=None):
        entry = {
            "idx": idx,
            "category": task.category,
            "prompt": task.prompt,
            "passed": passed,
            "reason": reason or "",
            "tool_calls": [tc.get("name", "") for tc in tool_calls],
            "latency": round(latency, 1),
            "response_preview": (agent_response or "")[:200],
        }
        if metadata:
            entry["metadata"] = metadata
            if metadata.get("state_leak"):
                self.state_leak_count += 1
            if metadata.get("cross_task_nav"):
                self.cross_task_nav_count += 1
        self.tasks.append(entry)
        cat = task.category
        self.category_results[cat]["total"] += 1
        if passed:
            self.category_results[cat]["pass"] += 1
        else:
            self.category_results[cat]["fail"] += 1
            self.failure_reasons[reason or "unknown"] += 1
        for tc in tool_calls:
            name = tc.get("name", "")
            self.tool_usage[name] += 1
            if tc.get("error"):
                self.tool_errors[name] += 1

    @property
    def total(self):
        return len(self.tasks)

    @property
    def passed(self):
        return sum(1 for t in self.tasks if t["passed"])

    @property
    def failed(self):
        return sum(1 for t in self.tasks if not t["passed"])

    @property
    def pass_rate(self):
        return (self.passed / self.total * 100) if self.total else 0

    def category_pass_rate(self, cat):
        r = self.category_results[cat]
        return (r["pass"] / r["total"] * 100) if r["total"] else 0

    def tool_selection_accuracy(self):
        """Percentage of tasks where at least one browser tool was selected."""
        browser_tools = {
            "browser_navigate", "browser_find", "browser_find_interactive",
            "browser_click", "browser_fill", "browser_press",
            "browser_snapshot", "browser_get_url", "browser_get_title",
            "browser_screenshot", "browser_current_state",
            "browser_evaluate", "browser_get_history", "browser_list_tabs",
            "browser_switch_tab", "browser_new_tab", "browser_close_tab",
            "browser_wait_visible", "browser_wait_text", "browser_wait_interactive",
            "browser_shadow_query", "browser_health", "vision_browser",
        }
        with_browser = sum(
            1 for t in self.tasks
            if any(tc in browser_tools for tc in t["tool_calls"])
        )
        return (with_browser / self.total * 100) if self.total else 0
