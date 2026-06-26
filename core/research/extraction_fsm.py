"""core/research/extraction_fsm.py
Research Extraction State Machine — deterministic extraction workflow control.

The FSM owns extraction sequencing (entity detection → splitting → attributes →
relations → normalization → validation → store). The LLM/extractor performs
bounded work within each state; the FSM decides progression, recovery, and
validation.

States:
  START              — initialize extraction context
  DETECT_ENTITIES    — identify candidate entities from text
  SPLIT_ENTITIES     — separate merged entity mentions
  EXTRACT_ATTRIBUTES — collect attributes for each entity
  EXTRACT_RELATIONS  — connect related entities
  NORMALIZE          — canonical names, units, dates
  VALIDATE           — confidence + duplicate checking
  STORE              — persist to FactStore
  COMPLETE           — terminal success
  FAIL               — terminal failure

Each state:
  - allowed_operations: which operations may be performed
  - exit_conditions: when to auto-transition
  - max_actions: max allowed iterations in this state
  - on_exit: target state on clean exit
  - on_failure: target state on timeout/error
"""

from __future__ import annotations

import logging
import time
import re
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ExtractionState(Enum):
    START = "START"
    DETECT_ENTITIES = "DETECT_ENTITIES"
    SPLIT_ENTITIES = "SPLIT_ENTITIES"
    EXTRACT_ATTRIBUTES = "EXTRACT_ATTRIBUTES"
    EXTRACT_RELATIONS = "EXTRACT_RELATIONS"
    NORMALIZE = "NORMALIZE"
    VALIDATE = "VALIDATE"
    STORE = "STORE"
    COMPLETE = "COMPLETE"
    FAIL = "FAIL"


# ── State definitions ──────────────────────────────────────────

STATE_DEFS: dict[ExtractionState, dict[str, Any]] = {
    ExtractionState.START: {
        "allowed_operations": {"initialize", "load_document"},
        "exit_operations": {"initialize"},
        "max_actions": 1,
        "on_exit": ExtractionState.DETECT_ENTITIES,
        "on_timeout": ExtractionState.FAIL,
        "on_failure": ExtractionState.FAIL,
        "prompt": "Starting extraction. Initialize context with source document.",
    },
    ExtractionState.DETECT_ENTITIES: {
        "allowed_operations": {"extract_entities", "read_source", "search_entities"},
        "exit_operations": {"extract_entities"},
        "max_actions": 3,
        "on_exit": ExtractionState.SPLIT_ENTITIES,
        "on_timeout": ExtractionState.SPLIT_ENTITIES,
        "on_failure": ExtractionState.FAIL,
        "prompt": "Detecting entities from source text.",
    },
    ExtractionState.SPLIT_ENTITIES: {
        "allowed_operations": {"split_entity", "merge_entity", "reject_entity"},
        "exit_operations": {"split_entity", "reject_entity"},
        "max_actions": 5,
        "on_exit": ExtractionState.EXTRACT_ATTRIBUTES,
        "on_timeout": ExtractionState.EXTRACT_ATTRIBUTES,
        "on_failure": ExtractionState.FAIL,
        "prompt": "Splitting or merging entity mentions.",
    },
    ExtractionState.EXTRACT_ATTRIBUTES: {
        "allowed_operations": {"extract_attribute", "skip_attribute", "read_source"},
        "exit_operations": {"extract_attribute"},
        "max_actions": 8,
        "on_exit": ExtractionState.EXTRACT_RELATIONS,
        "on_timeout": ExtractionState.EXTRACT_RELATIONS,
        "on_failure": ExtractionState.FAIL,
        "prompt": "Extracting attributes for detected entities.",
    },
    ExtractionState.EXTRACT_RELATIONS: {
        "allowed_operations": {"extract_relation", "skip_relation", "read_source"},
        "exit_operations": {"extract_relation"},
        "max_actions": 6,
        "on_exit": ExtractionState.NORMALIZE,
        "on_timeout": ExtractionState.NORMALIZE,
        "on_failure": ExtractionState.FAIL,
        "prompt": "Extracting relations between entities.",
    },
    ExtractionState.NORMALIZE: {
        "allowed_operations": {"normalize_name", "normalize_unit", "normalize_date", "normalize_value"},
        "exit_operations": {"normalize_name", "normalize_unit", "normalize_date"},
        "max_actions": 6,
        "on_exit": ExtractionState.VALIDATE,
        "on_timeout": ExtractionState.VALIDATE,
        "on_failure": ExtractionState.FAIL,
        "prompt": "Normalizing entity names, units, and dates.",
    },
    ExtractionState.VALIDATE: {
        "allowed_operations": {"check_duplicates", "check_confidence", "check_citations", "check_consistency"},
        "exit_operations": {"check_duplicates"},
        "max_actions": 4,
        "on_exit": ExtractionState.STORE,
        "on_timeout": ExtractionState.STORE,
        "on_failure": ExtractionState.FAIL,
        "prompt": "Validating extracted facts before storage.",
    },
    ExtractionState.STORE: {
        "allowed_operations": {"persist_facts", "persist_relations", "update_graph"},
        "exit_operations": {"persist_facts"},
        "max_actions": 2,
        "on_exit": ExtractionState.COMPLETE,
        "on_timeout": ExtractionState.FAIL,
        "on_failure": ExtractionState.FAIL,
        "prompt": "Storing validated facts and relations.",
    },
    ExtractionState.COMPLETE: {
        "allowed_operations": set(),
        "exit_operations": set(),
        "max_actions": 0,
        "on_exit": None,
        "on_timeout": None,
        "on_failure": None,
        "prompt": "Extraction complete.",
    },
    ExtractionState.FAIL: {
        "allowed_operations": {"read_source"},
        "exit_operations": set(),
        "max_actions": 1,
        "on_exit": None,
        "on_timeout": None,
        "on_failure": None,
        "prompt": "Extraction failed.",
    },
}


# ── Normalization patterns ─────────────────────────────────────

_DATE_PATTERNS = [
    (r"(\d{4})-(\d{2})-(\d{2})", lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}"),
    (r"(\w+)\s+(\d{1,2}),?\s*(\d{4})", lambda m: _month_to_num(m.group(1), m.group(2), m.group(3))),
    (r"(\d{1,2})\s+(\w+)\s+(\d{4})", lambda m: _month_to_num(m.group(2), m.group(1), m.group(3))),
]

_PRICE_PATTERN = re.compile(r"\$?(\d+(?:,\d{3})*(?:\.\d{2})?)")
_UNIT_PATTERNS = {
    "kilobytes": "KB", "megabytes": "MB", "gigabytes": "GB", "terabytes": "TB",
    "kilobits": "Kb", "megabits": "Mb", "gigabits": "Gb",
    "milliseconds": "ms", "seconds": "s", "minutes": "min",
    "kilometers": "km", "meters": "m", "centimeters": "cm",
    "kilogram": "kg", "grams": "g", "milligrams": "mg",
}

_DUPLICATE_CONFIDENCE_THRESHOLD = 0.85


# ── Context Factory ────────────────────────────────────────────


def _month_to_num(month: str, day: str, year: str) -> str:
    months = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "jun": "06", "jul": "07", "aug": "08", "sep": "09",
        "oct": "10", "nov": "11", "dec": "12",
    }
    m = months.get(month.lower().strip(".,"), "00")
    return f"{year}-{m}-{int(day):02d}"


def create_extraction_context(
    source_text: str = "",
    source_url: str = "",
    activity_id: str | None = None,
) -> dict[str, Any]:
    """Create a new extraction context."""
    return {
        "source_text": source_text,
        "source_url": source_url,
        "activity_id": activity_id,
        "entities": [],           # list of detected entity dicts
        "current_entity_index": 0,
        "attributes": {},         # entity_name -> list of attribute dicts
        "relations": [],          # list of relation dicts
        "normalizations": [],     # list of applied normalizations
        "validation_results": [], # list of validation results
        "stored_facts": [],       # fact_ids that were stored
        "stored_relations": [],   # relation_ids that were stored
        "errors": [],
        "start_time": 0.0,
    }


# ── Normalization helpers ─────────────────────────────────────

def normalize_entity_name(name: str) -> str:
    """Canonical entity name normalization."""
    name = name.strip()
    # Remove leading articles
    name = re.sub(r"^(?:the|a|an)\s+", "", name, flags=re.I)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name)
    # Remove trailing punctuation
    name = name.rstrip(".,;:!?")
    return name


def normalize_date_value(value: str) -> str:
    """Normalize date strings to YYYY-MM-DD format."""
    value = value.strip()
    for pattern, repl in _DATE_PATTERNS:
        m = re.search(pattern, value, re.I)
        if m:
            try:
                return repl(m)
            except Exception:
                pass
    # Already YYYY or YYYY-MM
    if re.match(r"^\d{4}(?:-\d{2})?(?:-\d{2})?$", value):
        return value
    return value


def normalize_unit(value: str) -> str:
    """Normalize unit names to canonical abbreviations."""
    for full, abbr in _UNIT_PATTERNS.items():
        value = re.sub(rf"\b{full}\b", abbr, value, flags=re.I)
    return value


def normalize_price(value: str) -> str:
    """Normalize price format."""
    m = _PRICE_PATTERN.search(value)
    if m:
        raw = m.group(1).replace(",", "")
        try:
            return f"${float(raw):.2f}"
        except ValueError:
            pass
    return value


# ── Duplicate detection ───────────────────────────────────────

def calculate_claim_similarity(claim_a: str, claim_b: str) -> float:
    """Simple word-overlap similarity for duplicate detection."""
    words_a = set(re.findall(r"\w+", claim_a.lower()))
    words_b = set(re.findall(r"\w+", claim_b.lower()))
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / max(len(union), 1)


def is_duplicate(existing_claims: list[str], new_claim: str, threshold: float = _DUPLICATE_CONFIDENCE_THRESHOLD) -> bool:
    """Check if a claim is a duplicate of existing claims."""
    for existing in existing_claims:
        similarity = calculate_claim_similarity(existing, new_claim)
        if similarity >= threshold:
            return True
    return False


# ── Research Extraction State Machine ─────────────────────────

class ExtractionFSM:
    """Deterministic state machine for research extraction workflow.

    Tracks current state, entities, attributes, relations, and validation.
    The extractor performs bounded work; the FSM owns sequencing and
    validation decisions.
    """

    def __init__(self, ctx: dict[str, Any] | None = None):
        self.state: ExtractionState = ExtractionState.START
        self.previous_state: ExtractionState | None = None
        self.actions_in_state: int = 0
        self.total_actions: int = 0
        self.transitions: list[dict[str, Any]] = []
        self.forced_transitions: int = 0
        self.loops_prevented: int = 0
        self.timeouts: int = 0
        self.validation_failures: int = 0
        self.history: list[dict[str, Any]] = []
        self.state_entry_time: float = time.time()
        self.last_state_transition_time: float = time.time()
        self.consecutive_same_entity: int = 0
        self.last_entity_name: str = ""
        self.consecutive_same_operation: int = 0
        self.last_operation: str = ""
        self.ctx: dict[str, Any] = ctx if ctx is not None else create_extraction_context()

    def get_def(self) -> dict[str, Any]:
        """Get the definition for the current state."""
        return STATE_DEFS.get(self.state, STATE_DEFS[ExtractionState.FAIL])

    def is_terminal(self) -> bool:
        """Check if FSM is in a terminal state."""
        return self.state in (ExtractionState.COMPLETE, ExtractionState.FAIL)

    def is_operation_allowed(self, operation: str) -> bool:
        """Check if an operation is allowed in the current state."""
        if self.is_terminal():
            return False
        allowed = self.get_def().get("allowed_operations", set())
        return operation in allowed

    def is_exit_operation(self, operation: str) -> bool:
        """Check if an operation triggers an exit transition."""
        return operation in self.get_def().get("exit_operations", set())

    def record_entity(self, name: str, entity_type: str = "unknown") -> dict:
        """Record a detected entity."""
        entity = {
            "name": name,
            "type": entity_type,
            "state": self.state.value,
            "time": time.time(),
        }
        self.ctx["entities"].append(entity)

        # Track consecutive same entity
        if name.lower() == self.last_entity_name.lower():
            self.consecutive_same_entity += 1
        else:
            self.consecutive_same_entity = 1
            self.last_entity_name = name

        return entity

    def record_attribute(self, entity: str, attribute: str, value: str) -> dict:
        """Record an extracted attribute for an entity."""
        attr = {
            "entity": entity,
            "attribute": attribute,
            "value": value,
            "normalized": False,
            "time": time.time(),
        }
        self.ctx["attributes"].setdefault(entity, []).append(attr)
        return attr

    def record_relation(self, source: str, target: str, relation_type: str) -> dict:
        """Record an extracted relation between entities."""
        rel = {
            "source": source,
            "target": target,
            "type": relation_type,
            "time": time.time(),
        }
        self.ctx["relations"].append(rel)
        return rel

    def record_normalization(self, entity: str, field: str, original: str, normalized: str) -> dict:
        """Record a normalization application."""
        norm = {
            "entity": entity,
            "field": field,
            "original": original,
            "normalized": normalized,
            "time": time.time(),
        }
        self.ctx["normalizations"].append(norm)
        return norm

    def record_validation(self, check: str, passed: bool, detail: str = "") -> dict:
        """Record a validation check result."""
        val = {
            "check": check,
            "passed": passed,
            "detail": detail,
            "time": time.time(),
        }
        self.ctx["validation_results"].append(val)
        if not passed:
            self.validation_failures += 1
        return val

    def record_action(self, operation: str, result: dict | None = None) -> None:
        """Record an operation and update state tracking."""
        now = time.time()

        # Auto-transition: START -> DETECT_ENTITIES on first operation
        if self.state == ExtractionState.START and operation in ("initialize", "load_document"):
            self.transition_to(ExtractionState.DETECT_ENTITIES)

        self.actions_in_state += 1
        self.total_actions += 1
        self.history.append({
            "operation": operation,
            "state": self.state.value,
            "time": now,
            "result": "success" if result and not result.get("error") else "error" if result else "unknown",
        })

        # Track consecutive same operation
        if operation == self.last_operation:
            self.consecutive_same_operation += 1
        else:
            self.consecutive_same_operation = 1
            self.last_operation = operation

        self.last_state_transition_time = now

    def check_loop(self) -> tuple[bool, str]:
        """Detect looping conditions.

        Returns (is_looping, reason) tuple.
        """
        # Same entity extracted 3+ times (entity-level loop)
        if self.consecutive_same_entity >= 3:
            self.loops_prevented += 1
            return True, f"same_entity:{self.last_entity_name}x{self.consecutive_same_entity}"

        # Same operation repeated 4+ times
        if self.consecutive_same_operation >= 4:
            self.loops_prevented += 1
            return True, f"same_operation:{self.last_operation}x{self.consecutive_same_operation}"

        # No new entities detected across multiple actions
        if self.state == ExtractionState.DETECT_ENTITIES and self.actions_in_state >= 3:
            if not self.ctx["entities"]:
                self.loops_prevented += 1
                return True, "no_entities_detected"

        # No attributes extracted across multiple actions
        if self.state == ExtractionState.EXTRACT_ATTRIBUTES and self.actions_in_state >= 4:
            total_attrs = sum(len(v) for v in self.ctx["attributes"].values())
            if total_attrs == 0:
                self.loops_prevented += 1
                return True, "no_attributes_extracted"

        # No relations extracted across multiple actions
        if self.state == ExtractionState.EXTRACT_RELATIONS and self.actions_in_state >= 4:
            if not self.ctx["relations"]:
                self.loops_prevented += 1
                return True, "no_relations_extracted"

        # Attribute already exists (duplicate attribute loop)
        if self.state == ExtractionState.EXTRACT_ATTRIBUTES and self.consecutive_same_operation >= 3:
            # Check if we keep extracting the same attribute for the same entity
            recent_attrs = list(self.ctx["attributes"].values())
            if recent_attrs and len(recent_attrs[-1]) >= 2:
                last_two = recent_attrs[-1][-2:]
                if len(last_two) == 2 and last_two[0]["attribute"] == last_two[1]["attribute"]:
                    self.loops_prevented += 1
                    return True, f"duplicate_attribute:{last_two[0]['attribute']}"

        return False, ""

    def check_timeout(self) -> bool:
        """Check if max actions exceeded for current state."""
        if self.is_terminal():
            return False
        max_actions = self.get_def().get("max_actions", 10)
        if self.actions_in_state >= max_actions:
            self.timeouts += 1
            return True
        return False

    def transition_to(self, new_state: ExtractionState, forced: bool = False) -> None:
        """Transition to a new state and reset action counter."""
        if new_state == self.state:
            return
        now = time.time()
        self.transitions.append({
            "from": self.state.value,
            "to": new_state.value,
            "forced": forced,
            "time": now,
            "actions_in_state": self.actions_in_state,
            "entities_found": len(self.ctx["entities"]),
            "attributes_found": sum(len(v) for v in self.ctx["attributes"].values()),
            "relations_found": len(self.ctx["relations"]),
        })
        self.previous_state = self.state
        self.state = new_state
        self.actions_in_state = 0
        self.consecutive_same_entity = 0
        self.last_entity_name = ""
        self.consecutive_same_operation = 0
        self.last_operation = ""
        self.state_entry_time = now
        self.last_state_transition_time = now
        if forced:
            self.forced_transitions += 1
        logger.debug("EFSM: %s -> %s%s", self.previous_state.value, new_state.value,
                     " (forced)" if forced else "")

    def handle_exit_operation(self, operation: str) -> ExtractionState | None:
        """Handle exit operation — returns target state if auto-transition applies."""
        if not self.is_exit_operation(operation):
            return None
        on_exit = self.get_def().get("on_exit")
        if on_exit:
            self.transition_to(on_exit)
            return on_exit
        return None

    def handle_timeout(self) -> ExtractionState | None:
        """Handle state timeout — returns fallback state, or None if terminal."""
        if self.is_terminal():
            return None
        on_timeout = self.get_def().get("on_timeout", ExtractionState.FAIL)
        if on_timeout is None:
            return None
        self.transition_to(on_timeout, forced=True)
        return on_timeout

    def handle_loop(self) -> ExtractionState | None:
        """Handle loop detection — returns target state for auto-advancement."""
        is_looping, reason = self.check_loop()
        if not is_looping:
            return None

        logger.info("EFSM loop detected: %s (state=%s)", reason, self.state.value)

        if self.state == ExtractionState.DETECT_ENTITIES:
            # Force advance to splitting even with few/no entities
            self.transition_to(ExtractionState.SPLIT_ENTITIES, forced=True)
            return ExtractionState.SPLIT_ENTITIES

        if self.state == ExtractionState.EXTRACT_ATTRIBUTES:
            # Force advance to relations even with few/no attributes
            self.transition_to(ExtractionState.EXTRACT_RELATIONS, forced=True)
            return ExtractionState.EXTRACT_RELATIONS

        if self.state == ExtractionState.EXTRACT_RELATIONS:
            # Force advance to normalization
            self.transition_to(ExtractionState.NORMALIZE, forced=True)
            return ExtractionState.NORMALIZE

        if self.state == ExtractionState.VALIDATE:
            # Force advance to store
            self.transition_to(ExtractionState.STORE, forced=True)
            return ExtractionState.STORE

        if self.state == ExtractionState.NORMALIZE:
            # Force advance to validate
            self.transition_to(ExtractionState.VALIDATE, forced=True)
            return ExtractionState.VALIDATE

        return None

    def get_prompt(self) -> str:
        """Get the guidance prompt for the current state."""
        defn = self.get_def()
        base = defn.get("prompt", "")
        entity_count = len(self.ctx["entities"])
        attr_count = sum(len(v) for v in self.ctx["attributes"].values())
        rel_count = len(self.ctx["relations"])
        return (f"{base} "
                f"[entities={entity_count} attrs={attr_count} rels={rel_count}]")

    def get_metrics(self) -> dict[str, Any]:
        """Get FSM metrics for benchmarking."""
        total_attrs = sum(len(v) for v in self.ctx["attributes"].values())
        total_norms = len(self.ctx["normalizations"])
        total_vals = len(self.ctx["validation_results"])
        failed_vals = sum(1 for v in self.ctx["validation_results"] if not v["passed"])
        duplicates_removed = sum(
            1 for v in self.ctx["validation_results"]
            if v["check"] == "check_duplicates" and v["passed"]
        )

        return {
            "efsm_final_state": self.state.value,
            "efsm_transitions": len(self.transitions),
            "efsm_forced_transitions": self.forced_transitions,
            "efsm_loops_prevented": self.loops_prevented,
            "efsm_timeouts": self.timeouts,
            "efsm_validation_failures": self.validation_failures,
            "efsm_total_actions": self.total_actions,
            "efsm_entities_found": len(self.ctx["entities"]),
            "efsm_attributes_extracted": total_attrs,
            "efsm_relations_extracted": len(self.ctx["relations"]),
            "efsm_normalizations_applied": total_norms,
            "efsm_validation_checks": total_vals,
            "efsm_validation_failures_count": failed_vals,
            "efsm_duplicates_removed": duplicates_removed,
            "efsm_transition_log": self.transitions[-20:] if self.transitions else [],
            "efsm_stored_facts": len(self.ctx["stored_facts"]),
        }

    def to_context_dict(self) -> dict[str, Any]:
        """Serialize FSM state for persistence."""
        return {
            "efsm_state": self.state.value,
            "efsm_previous_state": self.previous_state.value if self.previous_state else None,
            "efsm_actions_in_state": self.actions_in_state,
            "efsm_total_actions": self.total_actions,
            "efsm_transitions": self.transitions,
            "efsm_forced_transitions": self.forced_transitions,
            "efsm_loops_prevented": self.loops_prevented,
            "efsm_timeouts": self.timeouts,
            "efsm_validation_failures": self.validation_failures,
            "efsm_consecutive_same_entity": self.consecutive_same_entity,
            "efsm_last_entity_name": self.last_entity_name,
            "efsm_consecutive_same_operation": self.consecutive_same_operation,
            "efsm_last_operation": self.last_operation,
            "efsm_state_entry_time": self.state_entry_time,
            "efsm_last_state_transition_time": self.last_state_transition_time,
            "ctx": self.ctx,
        }

    @classmethod
    def from_context_dict(cls, data: dict[str, Any]) -> ExtractionFSM:
        """Restore FSM from a previously serialized context dict."""
        fsm = cls(ctx=data.get("ctx", create_extraction_context()))
        fsm.state = ExtractionState(data.get("efsm_state", "START"))
        prev = data.get("efsm_previous_state")
        if prev:
            fsm.previous_state = ExtractionState(prev)
        fsm.actions_in_state = data.get("efsm_actions_in_state", 0)
        fsm.total_actions = data.get("efsm_total_actions", 0)
        fsm.transitions = data.get("efsm_transitions", [])
        fsm.forced_transitions = data.get("efsm_forced_transitions", 0)
        fsm.loops_prevented = data.get("efsm_loops_prevented", 0)
        fsm.timeouts = data.get("efsm_timeouts", 0)
        fsm.validation_failures = data.get("efsm_validation_failures", 0)
        fsm.consecutive_same_entity = data.get("efsm_consecutive_same_entity", 0)
        fsm.last_entity_name = data.get("efsm_last_entity_name", "")
        fsm.consecutive_same_operation = data.get("efsm_consecutive_same_operation", 0)
        fsm.last_operation = data.get("efsm_last_operation", "")
        fsm.state_entry_time = data.get("efsm_state_entry_time", time.time())
        fsm.last_state_transition_time = data.get("efsm_last_state_transition_time", time.time())
        return fsm
