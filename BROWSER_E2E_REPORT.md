# Browser E2E Benchmark Report

**Model:** qwen2.5:7b  |  **Ollama:** http://127.0.0.1:11434
**Date:** 2026-06-24 00:46:15
**Tasks:** 100  |  **Passed:** 63  |  **Failed:** 37

---

## Overall Results

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Tool Selection Accuracy | 83.0% | >95% | [NO] |
| Workflow Completion | 63.0% | >80% | [NO] |
| End-to-End Success Rate | 63.0% | >75% | [NO] |

---

## Per Category

| Category | Pass | Total | Accuracy |
|----------|------|-------|----------|
| Documentation workflows        | 9/10 | 10 |  90.0% #########. |
| Form workflows                 | 8/10 | 10 |  80.0% ########.. |
| GitHub workflows               | 9/10 | 10 |  90.0% #########. |
| Information extraction         | 3/10 | 10 |  30.0% ###....... |
| Learning workflows             | 6/10 | 10 |  60.0% ######.... |
| Multi-page navigation          | 9/10 | 10 |  90.0% #########. |
| Recovery/error handling        | 3/10 | 10 |  30.0% ###....... |
| Research workflows             | 5/10 | 10 |  50.0% #####..... |
| Search workflows               | 6/10 | 10 |  60.0% ######.... |
| Shopping workflows             | 5/10 | 10 |  50.0% #####..... |

## Tool Usage

| Tool | Count |
|------|-------|
| browser_snapshot                    | 177 #################### |
| browser_navigate                    | 165 #################### |
| browser_evaluate                    | 104 #################### |
| browser_fill                        |  51 #################### |
| browser_press                       |  51 #################### |
| bash                                |   2 # |
| browser_click                       |   2 # |
| browser_find                        |   2 # |
| web_search                          |   1  |
| python                              |   1  |

## Failure Reasons

| Reason | Count |
|--------|-------|
| missing_search                           |  15 |
| too_few_calls:0<2                        |  10 |
| too_few_calls:0<1                        |   6 |
| missing_navigate                         |   4 |
| missing_verification:pip install         |   1 |
| too_few_calls:1<2                        |   1 |

## Per-Task Results

| # | Status | Category | Tools Used | Latency | Reason |
|---|--------|----------|------------|---------|--------|
|   0 | OK | Search workflows          | browser_press, browser_evaluate, browser |  93.7s |                                |
|   1 | NO | Search workflows          | none                                     |  59.7s | too_few_calls:0<1              |
|   2 | OK | Search workflows          | browser_press, browser_evaluate, browser |  45.4s |                                |
|   3 | NO | Search workflows          | none                                     |  45.0s | too_few_calls:0<1              |
|   4 | OK | Search workflows          | browser_press, browser_evaluate, browser |  41.5s |                                |
|   5 | OK | Search workflows          | browser_press, browser_evaluate, browser |  50.3s |                                |
|   6 | OK | Search workflows          | browser_press, browser_evaluate, browser |  36.6s |                                |
|   7 | OK | Search workflows          | browser_press, browser_evaluate, browser |  65.5s |                                |
|   8 | NO | Search workflows          | none                                     |  32.2s | too_few_calls:0<1              |
|   9 | NO | Search workflows          | browser_press, browser_evaluate, web_sea |  67.6s | missing_navigate               |
|  10 | OK | Documentation workflows   | browser_navigate, browser_snapshot       |  33.9s |                                |
|  11 | OK | Documentation workflows   | browser_press, browser_evaluate, browser |  53.0s |                                |
|  12 | OK | Documentation workflows   | browser_press, browser_evaluate, browser |  42.7s |                                |
|  13 | OK | Documentation workflows   | browser_navigate, browser_snapshot       |  39.9s |                                |
|  14 | OK | Documentation workflows   | browser_press, browser_evaluate, browser |  71.2s |                                |
|  15 | OK | Documentation workflows   | browser_navigate, browser_snapshot       |  41.8s |                                |
|  16 | OK | Documentation workflows   | browser_navigate, browser_snapshot       |  32.8s |                                |
|  17 | OK | Documentation workflows   | browser_press, browser_evaluate, browser |  54.6s |                                |
|  18 | OK | Documentation workflows   | browser_navigate, browser_snapshot       |  53.8s |                                |
|  19 | NO | Documentation workflows   | none                                     |  46.4s | too_few_calls:0<1              |
|  20 | OK | GitHub workflows          | browser_navigate, browser_snapshot       |  40.8s |                                |
|  21 | OK | GitHub workflows          | browser_press, browser_evaluate, browser |  45.3s |                                |
|  22 | OK | GitHub workflows          | browser_press, browser_evaluate, browser |  85.8s |                                |
|  23 | OK | GitHub workflows          | browser_press, browser_evaluate, browser | 130.3s |                                |
|  24 | OK | GitHub workflows          | browser_navigate, browser_snapshot       | 450.4s |                                |
|  25 | OK | GitHub workflows          | browser_press, browser_evaluate, browser | 100.6s |                                |
|  26 | OK | GitHub workflows          | browser_press, browser_evaluate, browser |  99.8s |                                |
|  27 | NO | GitHub workflows          | browser_press, browser_evaluate, browser |  96.3s | missing_verification:pip insta |
|  28 | OK | GitHub workflows          | browser_press, browser_evaluate, browser |  97.5s |                                |
|  29 | OK | GitHub workflows          | browser_press, browser_evaluate, browser |  65.4s |                                |
|  30 | OK | Research workflows        | browser_press, browser_evaluate, browser |  95.0s |                                |
|  31 | NO | Research workflows        | none                                     |  62.2s | too_few_calls:0<2              |
|  32 | NO | Research workflows        | none                                     |  54.1s | too_few_calls:0<2              |
|  33 | OK | Research workflows        | browser_press, browser_evaluate, browser |  59.4s |                                |
|  34 | OK | Research workflows        | browser_press, browser_evaluate, browser |  57.3s |                                |
|  35 | OK | Research workflows        | browser_press, browser_evaluate, browser |  90.8s |                                |
|  36 | NO | Research workflows        | none                                     |  39.9s | too_few_calls:0<2              |
|  37 | NO | Research workflows        | none                                     |  41.3s | too_few_calls:0<2              |
|  38 | OK | Research workflows        | browser_press, browser_evaluate, browser |  46.5s |                                |
|  39 | NO | Research workflows        | browser_evaluate, browser_navigate, brow |  55.3s | missing_search                 |
|  40 | OK | Shopping workflows        | browser_press, browser_evaluate, browser |  52.2s |                                |
|  41 | NO | Shopping workflows        | browser_evaluate, browser_navigate, brow |  50.2s | missing_search                 |
|  42 | OK | Shopping workflows        | browser_press, browser_evaluate, browser | 101.8s |                                |
|  43 | NO | Shopping workflows        | browser_evaluate, browser_navigate, brow |  75.2s | missing_search                 |
|  44 | OK | Shopping workflows        | browser_press, browser_evaluate, browser |  64.9s |                                |
|  45 | NO | Shopping workflows        | browser_evaluate, browser_navigate, brow |  55.6s | missing_search                 |
|  46 | NO | Shopping workflows        | browser_evaluate, browser_navigate, brow |  45.6s | missing_search                 |
|  47 | OK | Shopping workflows        | browser_press, browser_evaluate, browser |  49.0s |                                |
|  48 | NO | Shopping workflows        | browser_evaluate, browser_navigate, brow |  43.9s | missing_search                 |
|  49 | OK | Shopping workflows        | browser_press, browser_evaluate, browser |  65.5s |                                |
|  50 | OK | Learning workflows        | browser_press, browser_evaluate, browser |  85.1s |                                |
|  51 | OK | Learning workflows        | browser_navigate, browser_snapshot       |  52.3s |                                |
|  52 | NO | Learning workflows        | none                                     |  40.6s | too_few_calls:0<2              |
|  53 | NO | Learning workflows        | browser_evaluate, browser_navigate, brow |  86.3s | missing_search                 |
|  54 | OK | Learning workflows        | browser_press, browser_evaluate, browser |  92.2s |                                |
|  55 | OK | Learning workflows        | browser_press, browser_evaluate, browser |  78.7s |                                |
|  56 | NO | Learning workflows        | browser_evaluate, browser_navigate, brow | 187.5s | missing_search                 |
|  57 | OK | Learning workflows        | browser_press, browser_evaluate, browser |  57.6s |                                |
|  58 | NO | Learning workflows        | none                                     |  52.8s | too_few_calls:0<1              |
|  59 | OK | Learning workflows        | browser_press, browser_evaluate, browser |  56.4s |                                |
|  60 | OK | Form workflows            | browser_press, browser_evaluate, browser |  57.7s |                                |
|  61 | OK | Form workflows            | browser_press, browser_evaluate, browser |  87.9s |                                |
|  62 | OK | Form workflows            | browser_press, browser_evaluate, browser |  68.8s |                                |
|  63 | OK | Form workflows            | browser_press, browser_evaluate, browser |  63.6s |                                |
|  64 | NO | Form workflows            | browser_evaluate, browser_navigate, brow |  59.9s | missing_search                 |
|  65 | OK | Form workflows            | browser_press, browser_evaluate, browser |  87.0s |                                |
|  66 | OK | Form workflows            | browser_press, browser_evaluate, browser |  91.6s |                                |
|  67 | OK | Form workflows            | browser_press, browser_evaluate, browser |  64.0s |                                |
|  68 | OK | Form workflows            | browser_press, browser_evaluate, browser |  76.3s |                                |
|  69 | NO | Form workflows            | browser_evaluate, browser_navigate, brow |  72.0s | missing_search                 |
|  70 | OK | Multi-page navigation     | browser_press, browser_evaluate, browser |  54.5s |                                |
|  71 | OK | Multi-page navigation     | browser_press, browser_evaluate, browser |  47.1s |                                |
|  72 | OK | Multi-page navigation     | browser_press, browser_evaluate, browser |  68.7s |                                |
|  73 | OK | Multi-page navigation     | browser_press, browser_evaluate, browser | 111.1s |                                |
|  74 | OK | Multi-page navigation     | browser_evaluate, browser_navigate, brow |  66.8s |                                |
|  75 | NO | Multi-page navigation     | browser_evaluate, browser_navigate, brow |  97.3s | missing_search                 |
|  76 | OK | Multi-page navigation     | browser_press, browser_evaluate, browser |  77.6s |                                |
|  77 | OK | Multi-page navigation     | browser_evaluate, browser_navigate, brow |  99.1s |                                |
|  78 | OK | Multi-page navigation     | browser_evaluate, browser_navigate, brow |  52.4s |                                |
|  79 | OK | Multi-page navigation     | browser_press, browser_evaluate, browser |  47.7s |                                |
|  80 | OK | Information extraction    | browser_navigate, browser_snapshot       |  43.6s |                                |
|  81 | NO | Information extraction    | browser_press, browser_evaluate, bash, b |  68.4s | missing_navigate               |
|  82 | OK | Information extraction    | browser_press, browser_evaluate, browser | 111.9s |                                |
|  83 | NO | Information extraction    | none                                     |  41.8s | too_few_calls:0<1              |
|  84 | NO | Information extraction    | python                                   |  48.4s | too_few_calls:1<2              |
|  85 | OK | Information extraction    | browser_press, browser_evaluate, browser |  69.4s |                                |
|  86 | NO | Information extraction    | none                                     |  33.4s | too_few_calls:0<2              |
|  87 | NO | Information extraction    | none                                     |  40.8s | too_few_calls:0<2              |
|  88 | NO | Information extraction    | none                                     |  71.0s | too_few_calls:0<2              |
|  89 | NO | Information extraction    | none                                     |  47.5s | too_few_calls:0<2              |
|  90 | NO | Recovery/error handling   | browser_navigate, browser_snapshot       |  48.4s | missing_search                 |
|  91 | NO | Recovery/error handling   | browser_click                            |  44.3s | missing_navigate               |
|  92 | OK | Recovery/error handling   | browser_navigate, browser_snapshot       |  34.2s |                                |
|  93 | OK | Recovery/error handling   | browser_navigate, browser_snapshot       |  34.6s |                                |
|  94 | NO | Recovery/error handling   | browser_find                             |  55.6s | missing_navigate               |
|  95 | NO | Recovery/error handling   | browser_navigate, browser_snapshot       |  43.6s | missing_search                 |
|  96 | OK | Recovery/error handling   | browser_navigate, browser_snapshot       |  32.7s |                                |
|  97 | NO | Recovery/error handling   | none                                     |  35.1s | too_few_calls:0<2              |
|  98 | NO | Recovery/error handling   | browser_navigate, browser_snapshot       |  35.7s | missing_search                 |
|  99 | NO | Recovery/error handling   | browser_navigate, browser_snapshot       |  33.9s | missing_search                 |