# JARVIS AI OS — Architecture

## Overview

JARVIS is a multi-agent AI operating system with a modular plugin architecture, real-time communication channels, and a Flutter mobile companion.

## High-Level Diagram

```
┌──────────────────────────────────────────────────────┐
│                    Channels                           │
│  WhatsApp  Telegram  Discord  WebSocket  REST API     │
└────────────────────────┬─────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────┐
│                   Core Pipeline                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────┐ │
│  │ Router   │→ │  Brain   │→ │  Memory  │→ │Agent  │ │
│  │ (intent) │  │ (3-pass) │  │ (vector) │  │Loop   │ │
│  └──────────┘  └──────────┘  └──────────┘  └───────┘ │
└────────────────────────┬─────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────┐
│               Tools & Integrations                     │
│  MCP Servers  Composio  Browser  PC Control  Skills   │
└──────────────────────────────────────────────────────┘
```

## Key Components

### Core
- **llm_router.py**: LiteLLM-based router managing 6 model groups (chat, code, analysis, reasoning, vision, grader) with cloud fallback.
- **main.py**: FastAPI app with WebSocket support, middleware, and all route registrations.
- **agent_loop.py**: Main execution loop managing tool calls, MCP servers, and conversation context.

### Brain
- **UnifiedBrain.py**: Three-pass reasoning engine (reason → critique → revise) with plugin hooks.
- **reasoning_engine.py**: Core LLM interaction with structured output parsing.
- **cognitive_patterns.py**: Pattern-based planning, critique, and reflection.
- **epistemic_tagger.py**: Tags responses with provenance (RETRIEVED, VERIFIED, INFERRED, ASSUMED).

### Memory
- **memory.py**: Fact memory with JSON storage and embedding-based similarity search.
- **memory_vector.py**: Vector memory using ChromaDB or in-memory FAISS.
- **embeddings.py**: Embedding clients (HTTP API or local FastEmbed ONNX).

### Plugins
- **plugin_sdk/**: SDK for developing third-party plugins with hot-reload support.
- **plugin_registry**: Manages plugin lifecycle, hooks, and manifest validation.

### Channels
- WhatsApp, Telegram, Discord, SMS, and REST/WebSocket channels with unified message format.

### Skills
40+ built-in skills covering productivity, finance, entertainment, knowledge, and system control.
