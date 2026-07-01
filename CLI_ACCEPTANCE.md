# CLI Acceptance Examples — v3.0.0 GA

Every shipped command must have a documented invocation, expected output, and
exit code.  Run these as a regression checklist before tagging GA.

## How to Use

```powershell
# Run a single test
jarvis version

# Verify exit code
$LASTEXITCODE  # must be 0
```

---

## 1. `jarvis version`

**Expected:** Prints version string.  Exit 0.

```
> jarvis version
JARVIS v3.0.0-rc2
```

---

## 2. `jarvis setup`

**Expected:** Shows setup wizard or "already configured".  Exit 0.

```
> jarvis setup
Setup already configured.
```

---

## 3. `jarvis doctor`

**Expected:** Prints diagnostics panel.  Exit 0.

```
> jarvis doctor
Running JARVIS Production Doctor...
```

---

## 4. `jarvis demo`

**Expected:** Runs smoke test (creates hello.html, opens browser).  Exit 0.

```
> jarvis demo
JARVIS Demo...
```

---

## 5. `jarvis models list`

**Expected:** Lists configured models or empty table.  Exit 0.

```
> jarvis models list
No models configured.
```

---

## 6. `jarvis models test <model>`

**Expected:** Runs model inference test.  Exit 0.

```
> jarvis models test ollama/qwen2.5:7b
Testing ollama/qwen2.5:7b... OK (9251ms)
```

---

## 7. `jarvis models switch <mode>`

**Expected:** Switches model mode.  Exit 0.

```
> jarvis models switch local
Switched to local mode.
```

---

## 8. `jarvis models apikeys list`

**Expected:** Lists configured API keys (masked).  Exit 0.

```
> jarvis models apikeys list
openai: sk-****abc123
```

---

## 9. `jarvis settings get`

**Expected:** Shows current config.  Exit 0.

```
> jarvis settings get
model.mode = local
```

---

## 10. `jarvis settings set <key> <value>`

**Expected:** Sets config value.  Exit 0.

```
> jarvis settings set model.mode hybrid
Set model.mode = hybrid
```

---

## 11. `jarvis activity list`

**Expected:** Shows active activities or "No active activities."  Exit 0.

```
> jarvis activity list
No active activities.
```

---

## 12. `jarvis activity cleanup [hours]`

**Expected:** Marks stale RUNNING activities as FAILED.  Exit 0.

```
> jarvis activity cleanup 24
No stale RUNNING activities older than 24h found.
```

---

## 13. `jarvis server --dry-run`

**Expected:** Prints command without starting.  Exit 0.

```
> jarvis server --dry-run
[DRY RUN] Would start server: python -c uvicorn...
```

---

## 14. `jarvis doctor --json`

**Expected:** Prints JSON diagnostics.  Exit 0.

```
> jarvis doctor --json
{"status": "ok", ...}
```

---

## 15. `jarvis benchmark`

**Expected:** Runs performance baselines.  Exit 0.

```
> jarvis benchmark
Running JARVIS benchmark...
```

---

## 16. `jarvis provider list`

**Expected:** Lists execution providers.  Exit 0.

```
> jarvis provider list
Available providers:
```

---
