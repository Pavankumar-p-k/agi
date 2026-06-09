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

import logging

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = (
    "Summarize the following conversation in a concise paragraph. "
    "Keep all important facts, decisions, code changes, and user preferences. "
    "Write in third person past tense. Be specific about filenames, function names, and values."
)


def trim_for_context(messages: list, budget=None) -> list:
    """Trim messages to fit the given TokenBudget.
    
    budget can be a TokenBudget (from core.context_budget) or an int
    for backward compatibility.
    """
    if not messages:
        return messages
    # Backward compat: convert int to a simple budget
    if budget is None or isinstance(budget, (int, float)):
        try:
            from core.model_context import estimate_tokens as _et
        except ImportError:
            return messages
        hl = int(budget) - 512 if budget and budget > 512 else 0
        if hl <= 0:
            return messages[-1:]
        total = sum(_et(m) if isinstance(m, dict) else 0 for m in messages)
        if total <= hl:
            return messages
        trimmed = list(messages)
        while len(trimmed) > 1 and sum(_et(m) if isinstance(m, dict) else 0 for m in trimmed) > hl:
            trimmed.pop(0)
        return trimmed

    try:
        from core.model_context import estimate_tokens as _et
    except ImportError:
        return messages

    def _tk(m):
        return _et(m) if isinstance(m, dict) else 0

    # Split messages into protected vs evictable
    protected = [m for m in messages if m.get("_protected")]
    evictable = [m for m in messages if not m.get("_protected")]

    total_protected = sum(_tk(m) for m in protected)
    if total_protected >= budget.available:
        return protected + evictable[-1:]  # keep last evictable message

    evictable_budget = budget.available - total_protected

    # Identify recent pairs (last user + assistant messages)
    recent = []
    history = list(evictable)
    pairs_found = 0
    for i in range(len(evictable) - 1, -1, -1):
        recent.insert(0, evictable[i])
        if evictable[i].get("role") == "user":
            pairs_found += 1
            if pairs_found >= budget.recent_pairs:
                history = evictable[:i]
                break

    recent_tokens = sum(_tk(m) for m in recent)
    history_tokens = sum(_tk(m) for m in history)

    # Always keep recent within budget
    if recent_tokens + total_protected >= budget.available:
        return protected + recent

    # Compute how much room history gets
    history_budget = budget.available - total_protected - recent_tokens

    # Try LLM summarization on history
    if history_tokens > history_budget:
        compressed = _try_summarize(history, history_budget)
        if compressed is not None:
            return protected + compressed + recent

    # Drop oldest history messages until under budget
    trimmed = list(history)
    while len(trimmed) > 0 and sum(_tk(m) for m in trimmed) > history_budget:
        trimmed.pop(0)
    return protected + trimmed + recent


def _try_summarize(messages: list, budget_tokens: int) -> list | None:
    """Try to compress messages via LLM summarization. Returns None on failure."""
    try:
        from core.model_context import estimate_tokens as _et
    except ImportError:
        return None

    def _tk(m):
        return _et(m) if isinstance(m, dict) else 0

    if len(messages) < 3:
        return None

    parts = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content", "")
        if not content:
            continue
        if isinstance(content, list):
            texts = [b.get("text", "") for b in content if isinstance(b, dict)]
            content = "\n".join(texts)
        content_str = str(content)
        parts.append(f"[{role}]: {content_str[:2000]}")
    if not parts:
        return None

    source_text = "\n\n".join(parts)
    summary = _llm_summarize(source_text)
    if not summary:
        return None

    summary_msg = {"role": "system", "content": f"Previous conversation summary: {summary}"}
    if _tk(summary_msg) > budget_tokens:
        return None
    return [summary_msg]


def _llm_summarize(text: str) -> str | None:
    """Call the configured LLM to produce a single-paragraph summary.
    Uses the app's settings-based LLM configuration."""
    try:
        from core.settings_legacy import get_setting
        from core.llm_router import get_llm_endpoint
        endpoint = get_llm_endpoint()
        if not endpoint:
            logger.debug("[context_compactor] no LLM endpoint configured")
            return None
        model = get_setting("summary_model", "") or endpoint.get("model", "claude-3-5-haiku-latest")
        import json, urllib.request
        payload = {
            "model": model,
            "max_tokens": 512,
            "messages": [
                {"role": "system", "content": "You are a conversation summarizer. Be concise and factual."},
                {"role": "user", "content": f"{_SUMMARY_PROMPT}\n\n{text}"},
            ],
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            endpoint["url"], data=data,
            headers={"Content-Type": "application/json", **endpoint.get("headers", {})},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
        # Handle both OpenAI and Anthropic response formats
        if "choices" in body:
            return body["choices"][0]["message"]["content"].strip()
        if "content" in body:
            return body["content"][0]["text"].strip()
        return None
    except Exception as e:
        logger.warning("[context_compactor] LLM summarization failed: %s", e)
        return None
