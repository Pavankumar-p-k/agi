# RC3.3 — Scoring

Score each session 0–5 per metric after the session ends.

## Metrics

**1. Install success (5 = installed without help)**
- 5: `pip install jarvis-ai` worked on first try, no errors
- 4: Needed one minor correction (typo, missing pip)
- 3: Required guidance but succeeded
- 2: Failed initially, succeeded with help
- 1: Could not install
- 0: Did not attempt

**2. Setup completion (5 = completed without help)**
- 5: Completed setup without questions
- 4: Paused once but figured it out
- 3: Needed one hint
- 2: Needed multiple hints
- 1: Could not complete setup
- 0: Did not attempt setup

**3. Understands JARVIS purpose**
- 5: "It's an AI coding assistant" or similar within 30 seconds
- 4: Understood within 1 minute
- 3: Understood after exploring
- 2: Understood only after explaining
- 1: Never understood
- 0: Not assessed

**4. First task success (5 = completed independently)**
- 5: Completed a meaningful task within 5 minutes
- 4: Completed a meaningful task within 10 minutes
- 3: Made meaningful progress but didn't finish
- 2: Started but got stuck
- 1: Did not attempt
- 0: Could not start

**5. Exploration (5 = discovered 3+ features)**
- 5: Found demo, doctor, settings, and tried them
- 4: Found 2–3 features
- 3: Found 1 feature
- 2: Found features but didn't try them
- 1: Did not explore
- 0: Not applicable

**6. Frustration level (5 = no frustration)**
- 5: No frustration at any point
- 4: Brief moment of confusion, recovered
- 3: Moderate frustration, needed encouragement
- 2: Significant frustration
- 1: Extremely frustrated, nearly quit
- 0: Quit entirely

## Per-participant record

```
Participant #: ___
Background: _________
─────────────────────────
Install:       __ / 5
Setup:         __ / 5
Understanding: __ / 5
Task:          __ / 5
Exploration:   __ / 5
Frustration:   __ / 5
─────────────────────────
Total:         __ / 30
```

## Aggregate checklist

| Metric | Target | Pass | Notes |
|--------|--------|------|-------|
| Install success | >90% (avg >4.0) | | |
| Setup without help | >90% (avg >4.0) | | |
| Understand in <60s | >80% (avg >3.5) | | |
| First task <5 min | >60% (avg >3.0) | | |
| Exploration | >50% found 2+ features | | |
| Frustration | avg >3.0 | | |

**GA Gate:** All 6 pass → ready for GA.  
If 3+ metrics are red, fix UX before releasing.
