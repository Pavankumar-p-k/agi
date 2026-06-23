# CLI Feature Parity Report

Generated: 2026-06-14

## Navigation Structure

All 13 navigation items implemented as CLI subcommands:

| # | Nav Item     | Subcommand         | Status | Notes |
|---|--------------|--------------------|--------|-------|
| 1 | Home         | `jarvis home`      | ✅     | Dashboard overview |
| 2 | Chat         | `jarvis cli`       | ✅     | Interactive chat (pre-existing) |
| 3 | Voice        | `jarvis voice`     | ✅     | Voice dashboard |
| 4 | Models       | `jarvis models`    | ✅     | Extended with priority, assign, apikeys |
| 5 | Agents       | `jarvis agents`    | ✅     | Extended with list, health, run |
| 6 | Automation   | `jarvis automation`| ✅     | status, goals, repair, architectural |
| 7 | Memory       | `jarvis memory`    | ✅     | list, vector, failure, architectural, add, search |
| 8 | Skills       | `jarvis skill`     | ✅     | Pre-existing (list, create) |
| 9 | Plugins      | `jarvis plugin`    | ✅     | Pre-existing (full lifecycle) |
| 10 | Integrations | `jarvis integrations` | ✅  | list, connect, disconnect, health, config |
| 11 | Projects    | `jarvis project`   | ✅     | Pre-existing (list, create, show, delete) |
| 12 | Diagnostics | `jarvis diagnostics` | ✅   | models, integrations, voice, features — plus `jarvis doctor` |
| 13 | Settings    | `jarvis settings`  | ✅     | Pre-existing (get, set, reset, export, import) |

## Feature Registry (14)

| Command | Description | Status |
|---------|-------------|--------|
| `jarvis features` | List all features with status | ✅ |
| `jarvis features list` | List all features | ✅ |
| `jarvis features explore <slug>` | Show feature detail — description, status, health, requirements, config | ✅ |
| `jarvis features toggle <slug>` | Enable a feature | ✅ |
| `jarvis features toggle <slug> --off` | Disable a feature | ✅ |

## Model Management (7)

| Command | Description | Status |
|---------|-------------|--------|
| `jarvis models list` | List providers with status, latency, cost | ✅ (pre-existing) |
| `jarvis models test` | Test a provider | ✅ (pre-existing) |
| `jarvis models benchmark` | Benchmark latency | ✅ (pre-existing) |
| `jarvis models switch local\|cloud\|hybrid` | Switch mode | ✅ (pre-existing) |
| `jarvis models priority` | Show provider priority | ✅ **NEW** |
| `jarvis models assign [type] [model]` | Per-task model assignment | ✅ **NEW** |
| `jarvis models apikeys [list\|set\|delete]` | API key management | ✅ **NEW** |

## Integration Management (7)

| Integration     | Connect | Disconnect | Health | Config |
|-----------------|---------|------------|--------|--------|
| Gmail           | ✅      | ✅         | ✅     | ✅     |
| Telegram        | ✅      | ✅         | ✅     | ✅     |
| WhatsApp        | ✅      | ✅         | ✅     | ✅     |
| Discord         | ✅      | ✅         | ✅     | ✅     |
| Slack           | ✅      | ✅         | ✅     | ✅     |
| GitHub          | ✅      | ✅         | ✅     | ✅     |
| Google Drive    | ✅      | ✅         | ✅     | ✅     |

## Agent Dashboard (4)

| Command | Description | Status |
|---------|-------------|--------|
| `jarvis agents` | List all agents with status | ✅ |
| `jarvis agents list` | List all agents | ✅ |
| `jarvis agents health` | Agent health check | ✅ |
| `jarvis agents run <name> <task>` | Run an agent | ✅ (pre-existing) |

## Automation Dashboard (4)

| Command | Description | Status |
|---------|-------------|--------|
| `jarvis automation` | Show automation status | ✅ |
| `jarvis automation goals` | List active goals | ✅ |
| `jarvis automation repair` | Repair pattern memory | ✅ |
| `jarvis automation architectural` | Architectural memory | ✅ |

## Memory Dashboard (6)

| Command | Description | Status |
|---------|-------------|--------|
| `jarvis memory` | List memory entries | ✅ |
| `jarvis memory list` | List memory entries | ✅ |
| `jarvis memory vector` | Vector store status | ✅ |
| `jarvis memory failure` | Failure pattern memory | ✅ |
| `jarvis memory architectural` | Architectural memory | ✅ |
| `jarvis memory add <text>` | Add memory entry | ✅ |
| `jarvis memory search <query>` | Search memory entries | ✅ |

## Diagnostics Dashboard (5)

| Command | Description | Status |
|---------|-------------|--------|
| `jarvis diagnostics` | Run all diagnostics | ✅ |
| `jarvis diagnostics models` | Model provider health | ✅ |
| `jarvis diagnostics integrations` | Integration health | ✅ |
| `jarvis diagnostics voice` | Voice system health | ✅ |
| `jarvis diagnostics features` | Feature audit | ✅ |
| `jarvis doctor` | Full production doctor (pre-existing) | ✅ |

## Slash Commands (Interactive CLI)

New slash commands added to `cli_slash_commands.py`:

| Command | Description |
|---------|-------------|
| `/home` | Home dashboard |
| `/voice` | Voice dashboard |
| `/automation` | Automation dashboard |
| `/memory` | Memory entries |
| `/memory-add <text>` | Add memory entry |
| `/memory-search <query>` | Search memory |
| `/integrations` | Integration status |
| `/integrations health <name>` | Integration health check |
| `/integrations connect <name>` | Connect integration |
| `/integrations disconnect <name>` | Disconnect integration |

## Feature Parity Summary

| Metric | Count |
|--------|-------|
| Total CLI subcommands | 45 |
| New navigation subcommands | 7 (home, voice, automation, memory, integrations, features, diagnostics) |
| Enhanced subcommands | 3 (models, agents, voice) |
| Total CLI commands accessible | 13/13 navigation items |
| Feature registry exposed | 22/22 features |
| Integrations manageable | 7/7 |
| Dead stubs removed | 8 (`cmd_voice`, `cmd_cli_agents`, `cmd_agents` stub, `cmd_boot` stub, `cmd_tools` dupe, `cmd_mcp` dupe, `cmd_opencode` dupe, `cmd_gui_electron` dupe) |

## Backend APIs Wired

| Domain | Endpoints Wired | Status |
|--------|-----------------|--------|
| Feature Registry | GET /api/features, GET /api/features/{slug}, POST /api/features/{slug}/toggle | ✅ |
| Models | Hybrid platform, router, config_registry, api_key_vault | ✅ |
| Integrations | IntegrationManager (all 7 integrations) | ✅ |
| Agents | sub_agents/registry (all 10 agents) | ✅ |
| Memory | MemoryManager, PatternFailureMemory, ArchitecturalMemory, MemoryVectorStore | ✅ |
| Voice | Config registry, sounddevice, STT/TTS providers | ✅ |
| Diagnostics | diagnostics.py, feature_registry, model_providers, integration_manager | ✅ |
