# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] — 2026-06-09

### Features
- feat(core): new platform modules — agent runtime, LLM core, RAG, spawning, tools, MCP servers, multimodal, authz, gateway, graph, observability, persistence, plugins track3 (#1bb73f1)
- feat: complete 7-day overhaul — session mgmt, CLI overhaul, file agent, modular prompts, context hub, opencode delegate, tests (#774ecc3)
- Major overhaul: refactor core/main.py, add voice pipeline, temporal memory, crawl4ai/n8n/composio tools, LLM router; improve wake_word, privacy, brain cognition, world state, browser automation, and search tools (#27d15fd)
- feat(cli): CLI infrastructure rewrite — commands, server, state, requests, visuals (#6b5cd5f)
- feat(tui): terminal UI with input, file tree, and chat panels (#084f06d)
- feat(web): web UI client (#4c0fe46)
- feat(electron): desktop Electron shell (#f6b8d5c)
- Phase 1-8 upgrade: Voice, Privacy, Search, Memory, Tagging, Mobile, PC Control, Dashboard (#8a052e7)
- Unify chat pipeline, implement reminder scheduler and PC control (#a541508)
- Initial JARVIS - FastAPI + Ollama + Flutter AI Assistant (#0b4c6fa)

### Bug Fixes
- fix(voice): edge_tts module, fix missing awaits, broken imports, deprecated get_event_loop (#f1e0a14)
- fix(core): silence bare except blocks, fix undefined names, remove dead code — F821, F841, E722 across all modules (#9f2c949)
- fix: Ollama-first LLM routing, disable cloud failover by default (#6fcd170)
- fix: resolve SyntaxError from __future__ import annotations ordering (#982e2e6)
- Fix critical bugs: H1 play_media intent, H2 async chat, H3 orphaned intents, H5 file_manager, H9 multi-word open, H10 reminder regex, C4 browser imports, C5 httpx client, C6 asyncio.run (#c6171ce)
- Fix H7/H8: privacy routing for REST API, pass model from route_request through process_text (#be5ec5b)
- Modernize JARVIS: Fix chat pipeline, reminders, and PC control (#07adf3a)

### Documentation
- pre-launch: use cases doc, web UI fixes, launch checklist (#81d2473)
- v1.0 release: production-ready JARVIS AI OS (#9bab93e)

### Refactoring
- Merge remote: keep our engine.js fixes, accept remote config/changes (#145bc2e)

### Chores / Maintenance
- chore: switch from MIT to Apache 2.0 license (#b6e392c)
- chore: new configs, CI workflows, docs, tests, archive cleanup (#be3664c)
- Merge pull request #2 from Pavankumar-p-k/fix-chat-pipeline-reminders-pc-control (#a9a401e)
