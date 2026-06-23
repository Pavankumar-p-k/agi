# Cross-System Benchmark Report — v1
**Timestamp:** 2026-06-20T13:37:12.741795
**Session:** benchmark-4b8c5de5

## Summary
| Metric | Value |
|--------|-------|
| Tasks Passed | 10/10 (100.0%) |
| Steps Completed | 38/38 (100.0%) |
| Tool Calls | 38 |
| Failures | 0 |
| Handoff Failures | 0 |
| State Loss Events | 0 |
| Avg Latency | 62.7s |
| Latency Range | 3.7s - 144.2s |

## By System
| System | Task Pass Rate | Step Pass Rate |
|--------|---------------|----------------|
| Automation | 8/8 (100.0%) | 32/32 (100.0%) |
| Browser | 3/3 (100.0%) | 15/15 (100.0%) |
| Chat | 2/2 (100.0%) | 10/10 (100.0%) |
| Gmail | 3/3 (100.0%) | 14/14 (100.0%) |
| LLM | 1/1 (100.0%) | 2/2 (100.0%) |
| Memory | 3/3 (100.0%) | 15/15 (100.0%) |
| WhatsApp | 1/1 (100.0%) | 6/6 (100.0%) |

## Per-Task Results
| Task | Status | Steps | Latency | Handoffs | Failures |
|------|--------|-------|---------|----------|----------|
| research_build | PASS | 4/4 | 68.2s | 0 | - |
| build_email | PASS | 2/2 | 60.0s | 0 | - |
| build_validate_notify | PASS | 4/4 | 84.7s | 0 | - |
| memory_across_chats | PASS | 4/4 | 3.7s | 0 | - |
| build_repair_build | PASS | 3/3 | 144.2s | 0 | - |
| multi_model_chat | PASS | 2/2 | 18.1s | 0 | - |
| full_pipeline | PASS | 6/6 | 64.9s | 0 | - |
| state_churn | PASS | 6/6 | 60.2s | 0 | - |
| cancel_workflow | PASS | 2/2 | 61.6s | 0 | - |
| research_build_email | PASS | 5/5 | 61.9s | 0 | - |

## Step Details

### research_build (PASS)
| # | Tool | Result | Latency | Error |
|---|------|--------|---------|-------|
| 0 | browser_navigate | OK | 8.11s | - |
| 1 | browser_snapshot | OK | 0.06s | - |
| 2 | build_project | OK | 60.0s | - |
| 3 | run_tests | OK | 0.02s | - |

### build_email (PASS)
| # | Tool | Result | Latency | Error |
|---|------|--------|---------|-------|
| 0 | build_project | OK | 59.98s | - |
| 1 | run_tests | OK | 0.01s | - |

### build_validate_notify (PASS)
| # | Tool | Result | Latency | Error |
|---|------|--------|---------|-------|
| 0 | build_project | OK | 59.99s | - |
| 1 | runtime_validate | OK | 0.01s | - |
| 2 | repair_project | OK | 24.64s | - |
| 3 | manage_memory | OK | 0.02s | - |

### memory_across_chats (PASS)
| # | Tool | Result | Latency | Error |
|---|------|--------|---------|-------|
| 0 | manage_memory | OK | 0.02s | - |
| 1 | create_session | OK | 0.01s | - |
| 2 | manage_memory | OK | 3.66s | - |
| 3 | manage_memory | OK | 0.0s | - |

### build_repair_build (PASS)
| # | Tool | Result | Latency | Error |
|---|------|--------|---------|-------|
| 0 | build_project | OK | 60.0s | - |
| 1 | repair_project | OK | 24.2s | - |
| 2 | build_project | OK | 59.99s | - |

### multi_model_chat (PASS)
| # | Tool | Result | Latency | Error |
|---|------|--------|---------|-------|
| 0 | chat_with_model | OK | 18.1s | - |
| 1 | create_session | OK | 0.0s | - |

### full_pipeline (PASS)
| # | Tool | Result | Latency | Error |
|---|------|--------|---------|-------|
| 0 | browser_navigate | OK | 2.65s | - |
| 1 | browser_snapshot | OK | 0.59s | - |
| 2 | build_project | OK | 61.6s | - |
| 3 | run_tests | OK | 0.01s | - |
| 4 | runtime_validate | OK | 0.02s | - |
| 5 | manage_memory | OK | 0.01s | - |

### state_churn (PASS)
| # | Tool | Result | Latency | Error |
|---|------|--------|---------|-------|
| 0 | manage_memory | OK | 0.02s | - |
| 1 | manage_memory | OK | 0.01s | - |
| 1 | manage_memory | OK | 0.01s | - |
| 3 | create_session | OK | 0.0s | - |
| 4 | build_project | OK | 59.98s | - |
| 5 | manage_memory | OK | 0.12s | - |

### cancel_workflow (PASS)
| # | Tool | Result | Latency | Error |
|---|------|--------|---------|-------|
| 0 | build_project | OK | 61.57s | - |
| 1 | cancel_build | OK | 0.0s | - |

### research_build_email (PASS)
| # | Tool | Result | Latency | Error |
|---|------|--------|---------|-------|
| 0 | browser_navigate | OK | 1.82s | - |
| 1 | browser_snapshot | OK | 0.06s | - |
| 2 | build_project | OK | 60.0s | - |
| 3 | run_tests | OK | 0.02s | - |
| 4 | manage_memory | OK | 0.01s | - |

## Error Analysis
Total errors: 0
