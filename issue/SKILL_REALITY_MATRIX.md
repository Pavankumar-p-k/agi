# SKILL REALITY MATRIX
## Phase 6 — Runtime Audit Report
> Generated: 2026-06-10
> Source: C:\Users\peter\Desktop\jarvis

---

## Summary

| Category        | Count |
|-----------------|-------|
| Skills in library/ | 50 |
| Skills in installed/ | 0 |
| Skills in data/skills.json (registry) | 0 |
| Skills loaded by SkillManager | 50 (all from library/, but loaded=False) |
| Skills broken (malformed manifest) | 0 |
| Orphan skills (no registry entry) | 50 (ALL — no data/skills.json) |

---

## 1. Skill Inventory

### 1a. Library Skills (50 found in `skills/library/`)

| Category | Skills |
|----------|--------|
| **entertainment** (9) | games, joke, movie_rec, news, quiz, quote, recipe, sports, spotify, weather |
| **finance** (10) | bill_reminder, budget, crypto, expenses, gold_price, inflation, loan_emi, stocks, tax_calc, upi_gen |
| **knowledge** (10) | code_snippet, dictionary, fact_check, latex_math, paper_summarizer, regex_helper, sql_assistant, thesaurus, translator, wikipedia |
| **productivity** (10) | calendar, email_summarizer, github_issues, habit_tracker, linkedin_drafter, meeting_minutes, pdf_extractor, pomodoro, todoist, url_shortener |
| **system** (9) | clipboard, file_organizer, ip_lookup, password_gen, qr_gen, screenshot, speedtest, system_monitor, timer, unit_converter |

### 1b. Installed Skills (`skills/installed/`) — EMPTY

No skills are installed. The `skills/installed/` directory exists but is empty.

### 1c. Registry (`data/skills.json`) — DOES NOT EXIST

The SkillsManager (from `services/memory/skills.py`) loads skills from `data/skills.json`. This file does not exist, meaning:

- There are NO registered skills in the database
- The SkillsManager.get_relevant_skills() query will always return empty
- No skill matching (match_skill) can find anything

---

## 2. Skill Reality Check

| Skill | Installed? | Loaded? | Registered? | Callable? | Produces Output? | Status |
|-------|-----------|---------|-------------|-----------|-----------------|--------|
| All 50 library skills | NO (in library/, not installed/) | YES (SkillManager.load_all() finds them) | NO (no data/skills.json) | NO (no entry in SkillsManager registry) | NO (never triggered) | BROKEN |
| clipboard | NO | YES | NO | NO | NO | BROKEN |
| wikipedia | NO | YES | NO | NO | NO | BROKEN |
| calendar | NO | YES | NO | NO | NO | BROKEN |
| ... (all 50 same) | NO | YES | NO | NO | NO | BROKEN |

---

## 3. Findings

### 3a. Two Competing Skill Systems

There are TWO separate skill management systems in the codebase:

**System A: `skills/manager.py` — SkillManager (loadable packages)**
- Source: `skills/library/` with `skill.json` manifests + `main.py` handlers
- Loaded by: `SkillManager.load_all()` 
- Used by: None (no code calls `skill_manager.get()` or `get_all_tools()` in the agent loop)
- Capacity: 50 skills, all found by `load_all()`, all with `loaded=False` (entry_point exists but not fully executed)
- **Status: DEAD** — loads but nothing uses it

**System B: `services/memory/skills.py` — SkillsManager (database-backed)**
- Source: `data/skills.json`
- Loaded by: `SkillsManager.load(owner=...)` 
- Used by: `core/agent_prompts.py` in `_build_system_prompt()` (injects relevant skills into agent prompt)
- **Status: EMPTY** — `data/skills.json` doesn\'t exist, so no skills are ever injected

### 3b. Orphan Skills

All 50 library skills are ORPHANS — they have valid `skill.json` manifests and handler code, but:
- They are NOT in `skills/installed/`
- They are NOT registered in `data/skills.json`  
- Nothing calls `skill_manager.get("skillname")` to invoke them
- Nothing calls `SkillsManager.add_skill()` to register them

### 3c. SkillManager Load Issues

When `SkillManager.load_all()` runs, ALL 50 skills load but with `loaded=False`. The load process:
1. Reads `skill.json` ? (all 50 have valid JSON)
2. Finds `entry_point` (all reference `main.py`) ?  
3. Imports the Python file ? (no import errors)
4. Creates `Skill` instance ?
5. But `on_load()` is never called ? tools are never registered ? `is_loaded` stays False

The `on_load()` method in each skill\'s main.py registers tools via `self.register_tool()`, but since `on_load()` is never called, no tools are registered.

### 3d. Missing Features

- No `match_skill()` function exists anywhere in the codebase
- The `SkillsManager.get_relevant_skills()` uses fuzzy string matching (`SequenceMatcher`), not intent matching
- No trigger-based skill routing (no SKILL.md files found)
- No hot-reload mechanism wired into the agent loop

---

## 4. Broken Manifests

All 50 `skill.json` files were validated and ALL have valid JSON structure. No broken manifests found.

### 4a. Manifest Format (consistent across all 50):
```json
{
  "name": "category.skillname",
  "version": "1.0.0",
  "description": "JARVIS Skill for Skillname",
  "author": "JARVIS Core",
  "entry_point": "main.py",
  "enabled": true,
  "tools": ["toolname"]
}
```

No malformed JSON, no missing required fields. All have entry_point and tools arrays.

### 4b. Additional Files Found

| File | Path | Notes |
|------|------|-------|
| `plugin.json` | system/system_monitor/ | Additional config file, not part of skill spec |
| `plugin.json` | entertainment/weather/ | Additional config file |

---

## 5. Recommendations

1. **Unify the two skill systems** — Merge `skills/manager.py` (loadable packages) with `services/memory/skills.py` (database-backed registry)
2. **Install library skills** — Copy from `skills/library/` to `skills/installed/` or register in `data/skills.json`
3. **Wire SkillManager into agent loop** — Call `skill_manager.get()` from `execute_tool_block` when a skill tool is requested
4. **Create match_skill function** — Build intent-to-skill routing
5. **Call on_load()** — After importing skill modules, invoke `on_load()` so tools get registered

---
