# JARVIS — Product Definition

## Core Philosophy

Users think in goals. JARVIS thinks in capabilities. Providers are implementation details.

## What Is JARVIS?

A local-first AI workspace that completes real tasks instead of just answering questions. You tell it what you want to achieve. It plans the work, selects the right capabilities and providers, executes the task, and learns from the result — all while keeping you in control.

Under the hood, JARVIS is built as an AI Operating System: a goal-driven execution platform with deterministic planning, capability-based provider routing, permission-gated execution, and continuous learning.

## Who Is It For?

- **Developers** who want AI that runs on their hardware, understands their codebase, and automates their workflow
- **Anyone** who needs goals executed — build, research, automate, deploy, analyze — not just questions answered
- **People who care** about privacy, offline capability, and owning their own AI infrastructure

## How Is It Different?

| Dimension | JARVIS | ChatGPT / Claude |
|-----------|--------|------------------|
| Architecture | Goal→Capability→Provider→Execution→Learning | Single model, stateless |
| Local-first | ✓ (Ollama default) | ❌ Cloud-only |
| Provider routing | 8+ providers, selects best per task | One model per conversation |
| Self-improving | Every execution trains the system | No cross-session learning |
| Pipeline visible | Users see decisions being made | Black box |
| Subsystems | 60+ (32 hidden behind Developer Mode) | N/A |

## First 5 Minutes

1. `pip install jarvis-ai`
2. `jarvis` — auto-detects no config, launches setup wizard
3. Wizard checks: Python, Ollama, models, Playwright, GitHub, Email
4. Auto-launches 20-second demo: "Building hello.html"
5. Pipeline animates: Goal → Planner → Capability → Provider → Execution → Learning

## First 30 Minutes

1. Try: "Build a portfolio and deploy it"
2. Watch the pipeline live in Chat
3. Open Tasks to see all workflows
4. Open History to browse past executions
5. Open Explain after any task to see WHY decisions were made
6. Open Settings to configure models, themes, providers, permissions

## What It Cannot Do (v3)

- Self-modify its own source code
- Run on mobile as the primary interface
- Multi-user collaboration
- Provider plugin marketplace (v4)

## Roadmap Reference

See [ROADMAP.md](ROADMAP.md) for the prioritized plan.
