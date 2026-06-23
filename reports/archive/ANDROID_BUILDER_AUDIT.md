# ANDROID BUILDER AUDIT — Production-Grade APK Generation Pipeline

## Scope

Audit of the complete Android builder pipeline — LLM generation, deterministic repair, Gradle build, APK installation, and runtime validation. Covers `brain/automation/loop.py` (2504 lines), `brain/repair_modules/` (8 files), `core/pattern_failure_memory.py`, `core/failure_classifier.py`, and supporting infrastructure.

## Architecture Overview

```
LLM Prompt ──> Plan ──> Generate (Java + XML + Gradle)
                              │
                              ▼
                    Static Verification Gates
                     (manifest, layouts, imports)
                              │
                              ▼
                    Build Loop (up to 10 attempts)
                     ├── FailureMemory lookup
                     ├── classify_error() (25 regex patterns)
                     ├── apply_fix() (6 fix types)
                     ├── LLM analysis fallback
                     └── Browser search fallback
                              │
                              ▼
                    Test Loop
                              │
                              ▼
                    APK Install + Launch
                              │
                              ▼
                    Runtime Validation
                     (ADB screenshot + vision LLM)
```

## Current State Assessment

### What Works (Production-Grade)
| Component | Status | Evidence |
|-----------|--------|----------|
| LLM-based plan generation | **GOOD** | `_phase_plan()` generates tool-aware plans with Android-specific instructions |
| File generation | **GOOD** | `_phase_generate()` creates Java/XML/Gradle files, auto-stubs layouts and classes |
| Auto-stubbing | **GOOD** | `_autostub_missing_layouts()` + `_autostub_missing_classes()` catch `R.layout.X` and `new X()` references |
| Verification gates | **GOOD** | `verify_gates()` checks manifest, layouts, imports, gradle structure |
| Gradle fix generation | **GOOD** | `_fix_gradle_files()` writes proper build.gradle.kts, settings.gradle.kts, gradle.properties |
| Manifest fix | **GOOD** | `_fix_android_manifest()` ensures `<application>` + `<activity>` tags |
| Java fix (package, imports, @Override) | **GOOD** | `_fix_java_files()` fixes package decls, missing imports, Room/ViewModel/Nav imports |
| XML layout fix | **GOOD** | `_fix_xml_layouts()` escapes DataBinding, fixes xmlns |
| ADB detection + emulator start | **GOOD** | `_find_adb()`, `_adb_devices()`, `_find_avd()`, `_start_emulator()` |
| APK install + launch | **GOOD** | `_adb_install()`, `_adb_launch()`, `_extract_package_name()` |
| Runtime validation | **GOOD** | `_phase_runtime_validation()` captures screenshot, runs vision LLM |
| FailureMemory (loop.py) | **GOOD** | SQLite-backed pattern memory, auto-generalization, exact/prefix/pattern lookup |
| ArchitecturalMemory | **GOOD** | JSON-file-backed architectural pattern storage with plan mutation |

### What Needs Improvement

| Component | Issues |
|-----------|--------|
| **Error classifier** — 25 regex patterns only covers ~60% of javac error categories | Missing patterns for: Room annotation errors, Navigation graph errors, RecyclerView adapter issues, `@Override` duplicates, resource linkage errors, databinding errors, AAPT2 errors |
| **apply_fix()** — only 6 fix types | Missing: Room entity repair, Navigation graph generation, layout XML attribute fix, resource value fix, build.gradle.kts DSL fix, proguard fix |
| **Repair modules** — 8 standalone files not wired into loop | `brain/repair_modules/` has sophisticated modules but `loop.py` has its own simpler `apply_fix()` that doesn't call them |
| **PatternFailureMemory** — separate from FailureMemory | `core/pattern_failure_memory.py` (`PatternFailureMemory`) is not wired into `AutomationLoop` — only used by `FailureClassifier` |
| **No structured error format** | Errors stay as raw text — no normalization to `{file, line, category, symbol, message}` |
| **No Room-specific repairs** | Room `@Entity`, `@Dao`, `@Database` annotation errors, `Room.databaseBuilder()` issues |
| **No Navigation-specific repairs** | Missing `nav_graph.xml` generation, `NavHostFragment`, `NavController` issues |
| **No metric collection** | No build success rate, repair effectiveness, time-per-attempt tracking |
| **No benchmark automation** | No automated multi-app generation + build + report pipeline |

### Error Categories — Coverage Analysis

| Category | loop.py patterns | Repair module | Status |
|----------|-----------------|---------------|--------|
| Class/file mismatch | ❌ | `fix_class_names.py` | Module exists, not wired |
| Import name collision | ❌ | `fix_class_names.py` | Module exists, not wired |
| Missing import | ✅ partial | `fix_imports.py` | 80 known imports |
| Missing layout | ✅ | `fix_layouts.py` | |
| Missing ID | ❌ partial | `fix_layouts.py` | Module handles `@+id/X` |
| Missing drawable/color | ✅ partial | `fix_resources.py` | |
| Missing dependency | ✅ partial | `fix_dependencies.py` | 17 deps |
| Missing manifest activity | ✅ | `fix_manifest.py` | |
| `@Override` duplicate | ❌ | ❌ | Neither module nor loop pattern |
| Package mismatch | ❌ | `fix_class_names.py` | Module exists, not wired |
| Room annotation | ❌ | ❌ | Missing entirely |
| Navigation graph | ❌ | ❌ | Missing entirely |
| Gradle DSL syntax | ✅ partial | `fix_gradle.py` | |
| AAPT2 resource linking | ❌ | ❌ | Missing |

### PatternFailureMemory — Integration Status

`PatternFailureMemory` in `core/pattern_failure_memory.py` is a separate system from `FailureMemory` in `loop.py`:

| Aspect | FailureMemory (loop.py) | PatternFailureMemory (core/) |
|--------|------------------------|------------------------------|
| Backend | SQLite | JSON file |
| Generalization | Auto-generalizes on store | Manual `_generalize()` |
| Used by | `AutomationLoop._phase_build()` | `FailureClassifier.classify()` |
| Wired into loop | ✅ | ❌ |

### Test Coverage Gaps

| Area | Tests | Status |
|------|-------|--------|
| classify_error() | `test_classifier.py` | ✅ basic |
| FailureMemory | `test_classifier.py` | ✅ basic |
| Repair modules | None | ❌ |
| AutomationLoop._phase_build | None | ❌ |
| Runtime validation | None | ❌ |
| End-to-end APK generation | None | ❌ |

---

## Remediation Plan

### Phase 1 — Deterministic Repair Engine (Current)

1. Create `brain/compiler_repair_engine.py` — unified structured error parser + repair orchestrator
2. Add Room repair module (`brain/repair_modules/fix_room.py`)
3. Add Navigation repair module (`brain/repair_modules/fix_navigation.py`)
4. Add `@Override` dedup module (`brain/repair_modules/fix_override.py`)
5. Update `brain/repair_modules/__init__.py` to export all modules
6. Wire PatternFailureMemory into the engine
7. Wire engine into `AutomationLoop._phase_build()`

### Phase 2 — Benchmark Automation

8. Create `scripts/benchmark_android.py` — generate 5 apps, run pipeline, collect metrics
9. Generate benchmark report
10. Generate success rate report
11. Generate APK generation metrics

### Phase 3 — Continuous Improvement

12. Add AAPT2 error parsing
13. Add ProGuard/R8 rule generation
14. Add UI test generation
15. Add multi-module support

---

## Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `brain/automation/loop.py` | 2504 | Main autonomous build loop |
| `brain/compiler_repair_engine.py` | *new* | Unified deterministic repair engine |
| `core/pattern_failure_memory.py` | 153 | Generalized pattern failure memory |
| `core/failure_classifier.py` | 137 | Higher-level failure categorization |
| `brain/repair_modules/__init__.py` | 38 | Repair module registry |
| `brain/repair_modules/fix_imports.py` | 154 | 80 known Android imports |
| `brain/repair_modules/fix_gradle.py` | 86 | Build.gradle template |
| `brain/repair_modules/fix_dependencies.py` | 62 | 17 dependency mappings |
| `brain/repair_modules/fix_class_names.py` | 60 | Class/file mismatch, package mismatch |
| `brain/repair_modules/fix_manifest.py` | 41 | Manifest activity/permission repair |
| `brain/repair_modules/fix_layouts.py` | 53 | Missing layout XML creation |
| `brain/repair_modules/fix_resources.py` | 70 | Missing drawable/color/string creation |
| `brain/repair_modules/fix_room.py` | *new* | Room entity/dao/database repair |
| `brain/repair_modules/fix_navigation.py` | *new* | Navigation graph generation |
| `brain/repair_modules/fix_override.py` | *new* | @Override deduplication |
| `scripts/benchmark_android.py` | *new* | Benchmark harness |
