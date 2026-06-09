# JARVIS Hallucination Source Detection

## Top Hallucination Sources

1.  **Stateless Action Execution:** `execute_action` in `core/main.py` returns `{"executed": True}` regardless of actual system side-effects.
2.  **RAG Context Gaps:** When `memory.recall` returns nothing or irrelevant items, the LLM hallucinates context to fill the gaps in "Goal: {goal} Context: {context}".
3.  **Assumed Tool Success:** In `UnifiedBrain.three_pass`, the reasoning pass 1 might say "I'll open the browser", and if the critique pass doesn't catch it, the final answer says "I've opened the browser" even if no tool was actually called.
4.  **Implicit State Assumption:** The brain assumes the "current state" based on the prompt, not by querying system status (e.g., "What's playing right now?").

## Verdict
JARVIS "confuses past actions with current actions" because it doesn't have an execution log in its context. It only knows what it *said* it would do, not what the *tools* actually returned.
