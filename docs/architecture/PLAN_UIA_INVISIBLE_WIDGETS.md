# PLAN: UIA-Invisible Widget Fallback (autocomplete / custom combos)

Status: PROPOSED · Owner: jarvis desktop agent · Phase 2 follow-up

## 1. Problem

Some web controls are not reachable through UIA semantic discovery:

- **Autocomplete combos** (DemoQA State/City, React-select, Material-UI Autocomplete, Ant
  Select): the textbox is exposed, but the **dropdown option list is an overlay that UIA
  does not map to control elements**.
- **Canvas-rendered pickers** (charts, color/date wheels, drag-sliders): nothing is exposed.
- **Shadow-DOM widgets** with a closed shadow root.

Today the agent fills them with typed text + `Tab` order + `Enter`, which fails on widgets
that require an actual option click, and there is no verification that the selection landed.

## 2. Design goals

1. Zero new tool surface for the model: one new tool (`select_combo_option`) + no changes
   to the existing `list_form_fields` / `click_form_field` contract.
2. **Narrow OCR usage** per user guidance: OCR+click only when the keyboard macro fails to
   verify — never the default path.
3. Every failed interaction is logged as a drift event (existing `logs/element_drift.jsonl`),
   and learnings accumulate in the per-app allowlist registry.
4. No dependency is installed until the user approves (decision gate, §6).
5. Verification is mandatory after every selection attempt (vision `describe_screen` or UIA
   value read), never optimistic.

## 3. Proposed tool: `select_combo_option`

```
select_combo_option(app_name, field_label, option_text, wait_after=1.5)
```

Resolution order (first verified success wins):

1. **Anchor field via UIA** (`click_form_field`, which already self-heals via the element
   cache). Gives a stable pixel origin for the dropdown overlay.
2. **Keyboard macro** (zero deps): type `option_text` → wait → `ArrowDown` x N → `Enter`.
3. **OCR + text-anchored click** (narrow): screenshot the region below the anchor, OCR it,
   find the row whose OCR text ≈ `option_text`, click its center, re-check.
4. **Allowlist override** (zero deps): if app+control+option is already registered, run the
   recorded interaction (`macro` or `offset_click`) directly and return.

Every path returns the **verification result**:
`{success, verified, field_value, method: keyboard|ocr|allowlist, ocr_used: bool}`.
Failures append a structure-preserving record to the drift log and the app's allowlist entry
(suggested macro/offsets), so the next run is smarter.

## 4. Keyboard-only coverage (strategy 1) — no new dependency

Good news: most real-world autocompletes accept typed partial text + Enter/ArrowDown.
Target first: DemoQA State/City, a React-select, a MUI autocomplete, an <input list> datalist.
A matrix will be recorded per widget family so coverage is factual, not assumed.

Known hook for verification: after typing, the exposed textbox often still carries the typed
value — UIA value read is cheap. For single-select combos, `value` or the last typed string
is usually enough; vision is the backstop.

## 5. OCR dependency options (only if keyboard fails in practice)

Three candidates, ranked:

| # | Approach | Install cost | Notes |
|---|----------|--------------|-------|
| A | **WinRT OCR via PowerShell** (`Windows.Media.Ocr`) | none (Windows built-in), but needs async-unwrap coaxing from PS 5.1 | Zero-install; good enough for short dropdown labels (larger text). Lower accuracy on tiny text. |
| B | Python `winsdk` / `winrt` wheel + WinRT OCR | `pip install winsdk` (small) | Cleanest async API; cleanest Python integration; still no binary. |
| C | `pytesseract` + tesseract binary | pip + ~60 MB standalone exe (AGPL/OSS) | Best accuracy for small/lined text (`--psm 7` single line); heavier install, licensing note. |

Recommendation: try **A** first (zero cost); if quality is insufficient, jump to **B**;
keep **C** as the final fallback. Decision gate fired here before anything is installed.

## 6. Decision gate (user approves before implementation)

- [ ] Approve Phase 1 (keyboard macro + allowlist registry + verification hooks; no deps).
- [ ] If OCR needed: pick A / B / C and approve install.
- [ ] Approve the DemoQA State/City + 2 real-world widget families as the coverage test set.

## 7. Execution order (once approved)

1. Implement `select_combo_option` in `core/desktop/user_actions.py` (uses existing
   `_drift_recover`, `_log_drift`, element cache).
2. Register in `jarvis_desktop_agent.py` TOOLS (67 → 68; run the required tool audit first).
3. Risk tier: `select_combo_option` = `write-safe` (site state change, no data loss).
4. Add the allowlist registry as `data/combo_registry.json` (git-ignored like `element_cache.json`).
5. Test matrix: DemoQA State/City, React-select, MUI autocomplete, input-datalist → record
   per-family behavior in the registry DO_NOT_USE (plan-level note) / registry.
6. If OCR chosen: verify on all four families; document OCR row-rect → click mapping.

## 8. Exclusions

- No general screen-scraping or OCR-everything automation.
- No bypass of the consent/risk tier; `select_combo_option` stays `write-safe` (never
  destructive).
- No changes to the Phase 3 browser pipeline (it remains untouched until Phase 2 completes).