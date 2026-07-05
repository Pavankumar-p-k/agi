# ADR-003: Request Classifier Replaces Intent Router

**Status:** Accepted  
**Date:** 2026-07-05  
**Phase:** 1f  

## Context

Intent classification was done by `core/intent_router.py` — a 750-line rule-based function (`_rule_based()`) with keyword matching, regex patterns, and LLM fallback. It returned a dict with `{"intent", "target", "parameters"}`.

A newer `core/routing/request_classifier.py` existed with a hybrid keyword+LLM approach returning a typed `Classification(mode, confidence, sub_type)`.

These coexisted but were called from different paths, producing inconsistent results.

## Decision

**`core.routing.request_classifier.classify_request()` is the canonical intent classifier.**

1. `core/intent_router.py` → backward-compat shim; `extract_intent()` delegates to `classify_request()` with a `_legacy_intent()` mapping layer
2. Classification returns a `RequestMode` enum: CHAT, DIRECT, ACTION, CODEBASE, AGENT
3. ACTION requests include a `sub_type`: ACTION_FILE, ACTION_SHELL, ACTION_BROWSER, ACTION_SYSTEM
4. Keyword matching uses word-boundary-aware `_match_trigger()` to prevent false positives

## Consequences

**Positive:**
- Single classification pipeline with consistent enum output
- Word-boundary matching fixes false positives (e.g., "test" in "latest")
- 16 legacy intent strings preserved through mapping layer
- All 16 intent router unit tests pass

**Negative:**
- 3 production callers still import through the shim (channels/processor.py, websocket_server.py, routes/websocket.py)
- LLM-based classification requires Ollama running for keywords to be a fallback

**Migration:** `core/intent_router.py` to be removed in v4.0 after callers migrate to `classify_request()`.
