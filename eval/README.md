# Evaluation Framework

Scenario-based eval harness for testing agent behavior across tasks, tool use, reasoning, and edge cases.

## Scenario format (YAML)

```yaml
scenarios:
  - id: smoke-direct-answer
    name: "Simple direct answer (no tools)"
    prompt: "What is 2 + 2?"
    expected_patterns: ["4"]                      # regex patterns in final response
    forbidden_tools: ["web_search", "bash"]       # tools that must NOT be called
    max_rounds: 2
    tags: ["smoke", "qa"]

  - id: search-current-event
    name: "Web search for current info"
    prompt: "Who won the latest Formula 1 race?"
    expected_tools: ["web_search"]                # tools that MUST be called
    min_rounds: 1                                 # min agent rounds required
    tags: ["search", "knowledge"]

  - id: hitl-bash-command
    name: "HITL: bash command with pause enabled"
    prompt: "Run 'ls -la' to list files"
    expected_tools: ["bash"]
    tags: ["hitl", "effectful"]
    extra_params:
      pause_before_effectful: true                # passed to stream_agent_loop kwargs
```

Fields: `id`, `prompt`, `name` (defaults to id), `expected_tools`, `forbidden_tools`, `expected_patterns`, `forbidden_patterns`, `min_rounds`, `max_rounds` (default 10), `tags`, `model_override`, `extra_params`.

## CLI

```bash
# Run scenarios
python -m eval.cli run eval/scenarios/basic.yml --model gpt-4 --endpoint https://api.openai.com

# Run with custom output path
python -m eval.cli run eval/scenarios/ --model gpt-4 --concurrency 4 --output results.json

# Compare two result files
python -m eval.cli compare baseline.json current.json
```

## Scoring

Each scenario gets an `aggregate` score (0.0—1.0), passing if >= 0.7:

- **Tool call accuracy** (25%) — ratio of expected tools found; halved if forbidden tools called
- **Pattern match** (25%) — ratio of expected regex patterns found in response
- **Quality score** (30%) — LLM-as-judge via `QualityGrader` (falls back to 0.5 if unavailable)
- **Efficiency** (20%) — round-based penalty: `1 - (rounds / max_rounds)`; 1.0 if `min_rounds` met

## Tagging conventions

| Tag | Purpose |
|-----|---------|
| `smoke` | Quick sanity checks (2-3 rounds max) |
| `qa` | Direct Q&A, no tools needed |
| `code` | Code generation / explanation |
| `search` | Web search required |
| `memory` | Memory store / recall |
| `file` | File read / write |
| `tool` | Tool selection behavior |
| `hitl` | Human-in-the-loop (pause/resume) |
| `reasoning` | Multi-step / chain-of-thought |
| `multi-tool` | Requires 2+ different tools |
| `edge` | Edge cases (empty prompt, loops, timeouts) |
| `constraint` | Must work without certain tools |
| `effectful` | Destructive / mutating operations |
| `multi-hop` | Requires composing search results |
| `math` | Calculation or numeric reasoning |

## Runner

`eval/runner.py` calls `core.agent_loop.stream_agent_loop` for each scenario, collecting events, tool calls, response text, and duration. Supports configurable concurrency via `asyncio.Semaphore`.

## Results

Output is a JSON array of `ScenarioResult` objects. A companion `.report.json` is written alongside with aggregates and per-scenario pass/fail. Use `compare` subcommand to diff two runs — it lists regressions (score drop > 0.1), improvements (score gain > 0.1), new failures, and new passes.

## A/B Evaluation

`train/ab_eval.py` compares a base model against a fine-tuned model on 10 benchmark queries, scoring responses via `QualityGrader`. Returns a `deploy` decision if the fine-tuned model's mean score >= baseline and its minimum score >= 90% of baseline's minimum.
