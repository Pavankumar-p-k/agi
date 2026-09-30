"""Research Extraction FSM — supervised entity/attribute/relation extraction.

A deterministic finite state machine that walks a document through
detection, splitting, attribute/relation extraction, normalization,
validation and storage. Loop detection and action budgets keep it from
spinning, and the whole context is serializable so a run can resume.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

_DUPLICATE_CONFIDENCE_THRESHOLD = 0.8


class ExtractionState(str, Enum):
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


_LOOP_TARGETS = {
    ExtractionState.DETECT_ENTITIES: ExtractionState.SPLIT_ENTITIES,
    ExtractionState.SPLIT_ENTITIES: ExtractionState.EXTRACT_ATTRIBUTES,
    ExtractionState.EXTRACT_ATTRIBUTES: ExtractionState.EXTRACT_RELATIONS,
    ExtractionState.EXTRACT_RELATIONS: ExtractionState.NORMALIZE,
    ExtractionState.NORMALIZE: ExtractionState.VALIDATE,
    ExtractionState.VALIDATE: ExtractionState.STORE,
}

STATE_DEFS: Dict[ExtractionState, Dict[str, Any]] = {
    ExtractionState.START: {
        "allowed_operations": ["initialize", "load_document"],
        "exit_operations": ["initialize"],
        "max_actions": 3,
        "on_exit": ExtractionState.DETECT_ENTITIES,
        "on_timeout": ExtractionState.DETECT_ENTITIES,
        "on_loop": ExtractionState.DETECT_ENTITIES,
        "prompt": "Starting extraction. Load the document and locate entities.",
    },
    ExtractionState.DETECT_ENTITIES: {
        "allowed_operations": ["extract_entities", "read_source"],
        "exit_operations": ["extract_entities"],
        "max_actions": 3,
        "on_exit": ExtractionState.SPLIT_ENTITIES,
        "on_timeout": ExtractionState.SPLIT_ENTITIES,
        "on_loop": ExtractionState.SPLIT_ENTITIES,
        "prompt": "Detect entities in the source document.",
    },
    ExtractionState.SPLIT_ENTITIES: {
        "allowed_operations": ["split_entity", "read_source"],
        "exit_operations": ["split_entity"],
        "max_actions": 3,
        "on_exit": ExtractionState.EXTRACT_ATTRIBUTES,
        "on_timeout": ExtractionState.EXTRACT_ATTRIBUTES,
        "on_loop": ExtractionState.EXTRACT_ATTRIBUTES,
        "prompt": "Split compound entities into atomic entities.",
    },
    ExtractionState.EXTRACT_ATTRIBUTES: {
        "allowed_operations": ["extract_attribute", "read_source"],
        "exit_operations": ["extract_attribute"],
        "max_actions": 5,
        "on_exit": ExtractionState.EXTRACT_RELATIONS,
        "on_timeout": ExtractionState.EXTRACT_RELATIONS,
        "on_loop": ExtractionState.EXTRACT_RELATIONS,
        "prompt": "Extract attributes for the detected entities.",
    },
    ExtractionState.EXTRACT_RELATIONS: {
        "allowed_operations": ["extract_relation", "read_source"],
        "exit_operations": ["extract_relation"],
        "max_actions": 5,
        "on_exit": ExtractionState.NORMALIZE,
        "on_timeout": ExtractionState.NORMALIZE,
        "on_loop": ExtractionState.NORMALIZE,
        "prompt": "Extract relations between entities.",
    },
    ExtractionState.NORMALIZE: {
        "allowed_operations": ["normalize_name", "read_source"],
        "exit_operations": ["normalize_name"],
        "max_actions": 6,
        "on_exit": ExtractionState.VALIDATE,
        "on_timeout": ExtractionState.VALIDATE,
        "on_loop": ExtractionState.VALIDATE,
        "prompt": "Normalize dates, units, prices and entity names.",
    },
    ExtractionState.VALIDATE: {
        "allowed_operations": ["check_duplicates", "check_confidence", "check_citations"],
        "exit_operations": ["check_duplicates"],
        "max_actions": 5,
        "on_exit": ExtractionState.STORE,
        "on_timeout": ExtractionState.STORE,
        "on_loop": ExtractionState.STORE,
        "prompt": "Validate extracted facts: duplicates, confidence and citations.",
    },
    ExtractionState.STORE: {
        "allowed_operations": ["persist_facts", "read_source"],
        "exit_operations": ["persist_facts"],
        "max_actions": 3,
        "on_exit": ExtractionState.COMPLETE,
        "on_timeout": ExtractionState.COMPLETE,
        "on_loop": ExtractionState.COMPLETE,
        "prompt": "Persist validated facts to storage.",
    },
    ExtractionState.COMPLETE: {
        "allowed_operations": [],
        "exit_operations": [],
        "max_actions": 0,
        "on_exit": None,
        "on_timeout": None,
        "on_loop": None,
        "prompt": "Extraction complete.",
    },
    ExtractionState.FAIL: {
        "allowed_operations": [],
        "exit_operations": [],
        "max_actions": 0,
        "on_exit": None,
        "on_timeout": None,
        "on_loop": None,
        "prompt": "Extraction failed.",
    },
}

_TERMINAL = (ExtractionState.COMPLETE, ExtractionState.FAIL)

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_UNIT_MAP = {
    "kilobyte": "KB", "kilobytes": "KB", "kb": "KB",
    "megabyte": "MB", "megabytes": "MB", "mb": "MB",
    "gigabyte": "GB", "gigabytes": "GB", "gb": "GB",
    "terabyte": "TB", "terabytes": "TB", "tb": "TB",
    "millisecond": "ms", "milliseconds": "ms", "ms": "ms",
    "second": "s", "seconds": "s",
    "kilometer": "km", "kilometers": "km", "km": "km",
    "meter": "m", "meters": "m",
}

_ARTICLES = ("the ", "a ", "an ")


def normalize_entity_name(name: str) -> str:
    """Trim, strip a leading article and tidy whitespace/punctuation."""
    text = " ".join(str(name or "").split()).strip()
    if not text:
        return ""
    lowered = text.lower()
    for article in _ARTICLES:
        if lowered.startswith(article):
            text = text[len(article):].strip()
            break
    text = text.rstrip(".,;:!?")
    return " ".join(text.split()).strip()


def normalize_date_value(value: str) -> str:
    """Normalize common date spellings to ISO (YYYY-MM-DD) when possible."""
    text = str(value or "").strip()
    if not text:
        return text
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    if re.fullmatch(r"\d{4}", text):
        return text
    match = re.fullmatch(r"([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})", text)
    if match and match.group(1).lower() in _MONTHS:
        month = _MONTHS[match.group(1).lower()]
        return f"{int(match.group(3)):04d}-{month:02d}-{int(match.group(2)):02d}"
    match = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\.?,?\s+(\d{4})", text)
    if match and match.group(2).lower() in _MONTHS:
        month = _MONTHS[match.group(2).lower()]
        return f"{int(match.group(3)):04d}-{month:02d}-{int(match.group(1)):02d}"
    return text


def normalize_unit(value: str) -> str:
    """Normalize spelled-out units: '512 megabytes' -> '512 MB'."""
    text = str(value or "").strip()
    match = re.fullmatch(r"([\d.,]+)\s*([A-Za-z]+)", text)
    if not match:
        return text
    unit = _UNIT_MAP.get(match.group(2).lower())
    if not unit:
        return text
    number = match.group(1).rstrip(".")
    return f"{number} {unit}"


def normalize_price(value: str) -> str:
    """Normalize prices to $N.NN form; leave non-numeric text alone."""
    text = str(value or "").strip()
    match = re.search(r"\$?\s*([\d,]+(?:\.\d+)?)", text)
    if not match:
        return text
    number = match.group(1).replace(",", "")
    try:
        amount = float(number)
    except ValueError:
        return text
    return f"${amount:.2f}"


def _token_set(text: str) -> set:
    return {token for token in re.findall(r"[a-z0-9.]+", str(text or "").lower())
            if token}


def calculate_claim_similarity(claim_a: str, claim_b: str) -> float:
    """Dice similarity over word tokens (0.0-1.0)."""
    a = _token_set(claim_a)
    b = _token_set(claim_b)
    if not a or not b:
        return 0.0
    overlap = len(a & b)
    return (2 * overlap) / (len(a) + len(b))


def is_duplicate(existing_claims: List[str], new_claim: str) -> bool:
    """True when *new_claim* is a near-duplicate of any existing claim."""
    if not existing_claims:
        return False
    return any(calculate_claim_similarity(claim, new_claim)
               >= _DUPLICATE_CONFIDENCE_THRESHOLD for claim in existing_claims)


def create_extraction_context(source_text: str = "", source_url: str = "",
                              source_title: str = "",
                              query: str = "") -> Dict[str, Any]:
    """Fresh extraction context dictionary."""
    return {
        "source_text": source_text,
        "source_url": source_url,
        "source_title": source_title,
        "query": query,
        "entities": [],
        "attributes": {},
        "relations": [],
        "normalizations": [],
        "validation_results": [],
        "stored_facts": [],
    }


class ExtractionFSM:
    """Supervised extraction state machine with loop/timeout guards."""

    def __init__(self, ctx: Optional[Dict[str, Any]] = None) -> None:
        self.ctx: Dict[str, Any] = dict(ctx) if ctx is not None else create_extraction_context()
        self.state: ExtractionState = ExtractionState.START
        self.history: List[Dict[str, Any]] = []
        self.transitions: List[Dict[str, Any]] = []
        self.total_actions = 0
        self.actions_in_state = 0
        self.consecutive_same_operation = 0
        self.consecutive_same_entity = 0
        self.last_entity_name = ""
        self.last_operation = ""
        self.validation_failures = 0
        self.forced_transitions = 0
        self.loops_prevented = 0
        self.timeouts = 0

    # ── state queries ────────────────────────────────────────────────
    def is_terminal(self) -> bool:
        return self.state in _TERMINAL

    def is_operation_allowed(self, operation: str) -> bool:
        if self.is_terminal():
            return False
        return operation in STATE_DEFS[self.state]["allowed_operations"]

    def is_exit_operation(self, operation: str) -> bool:
        if self.is_terminal():
            return False
        return operation in STATE_DEFS[self.state]["exit_operations"]

    @property
    def _max_actions(self) -> int:
        return int(STATE_DEFS[self.state]["max_actions"])

    # ── state transitions ────────────────────────────────────────────
    def transition_to(self, new_state: ExtractionState,
                      forced: bool = False) -> Optional[ExtractionState]:
        if new_state == self.state:
            return None
        old_state = self.state
        self.state = new_state
        self.actions_in_state = 0
        self.consecutive_same_operation = 0
        self.transitions.append({
            "from": old_state.value,
            "to": new_state.value,
            "forced": bool(forced),
        })
        if forced:
            self.forced_transitions += 1
        return self.state

    def handle_exit_operation(self, operation: str) -> Optional[ExtractionState]:
        if not self.is_exit_operation(operation):
            return None
        target = STATE_DEFS[self.state]["on_exit"]
        if target is None:
            return None
        return self.transition_to(target)

    # ── recording ────────────────────────────────────────────────────
    def record_action(self, operation: str) -> None:
        self.history.append({"operation": operation, "state": self.state.value})
        self.total_actions += 1
        self.actions_in_state += 1
        if operation == self.last_operation:
            self.consecutive_same_operation += 1
        else:
            self.consecutive_same_operation = 1
        self.last_operation = operation
        # The initialize action leaves START on its own.
        if self.state == ExtractionState.START and operation == "initialize":
            self.transition_to(ExtractionState.DETECT_ENTITIES)

    def record_entity(self, name: str, entity_type: str = "entity") -> None:
        self.ctx.setdefault("entities", []).append(
            {"name": name, "type": entity_type})
        if name == self.last_entity_name:
            self.consecutive_same_entity += 1
        else:
            self.consecutive_same_entity = 1
        self.last_entity_name = name

    def record_attribute(self, entity: str, attribute: str, value: Any) -> None:
        bucket = self.ctx.setdefault("attributes", {}).setdefault(entity, [])
        bucket.append({"entity": entity, "attribute": attribute, "value": value})

    def record_relation(self, source: str, target: str, relation_type: str) -> None:
        self.ctx.setdefault("relations", []).append(
            {"source": source, "target": target, "type": relation_type})

    def record_normalization(self, entity: str, field: str,
                             original: Any, normalized: Any) -> None:
        self.ctx.setdefault("normalizations", []).append({
            "entity": entity, "field": field,
            "original": original, "normalized": normalized,
        })

    def record_validation(self, check: str, passed: bool, reason: str = "") -> None:
        self.ctx.setdefault("validation_results", []).append({
            "check": check, "passed": bool(passed), "reason": reason})
        if not passed:
            self.validation_failures += 1

    # ── guards ───────────────────────────────────────────────────────
    def check_loop(self) -> Tuple[bool, str]:
        if self.consecutive_same_entity >= 3:
            return True, "same_entity"
        if self.state == ExtractionState.EXTRACT_ATTRIBUTES and self._has_duplicate_attribute():
            return True, "duplicate_attribute"
        if self.consecutive_same_operation >= 4:
            return True, "same_operation"
        if self.state == ExtractionState.DETECT_ENTITIES:
            if self.actions_in_state >= 3 and not self.ctx.get("entities"):
                return True, "no_entities"
        if self.state == ExtractionState.EXTRACT_ATTRIBUTES:
            if self.actions_in_state >= 4 and not self.ctx.get("attributes"):
                return True, "no_attributes"
        if self.state == ExtractionState.EXTRACT_RELATIONS:
            if self.actions_in_state >= 4 and not self.ctx.get("relations"):
                return True, "no_relations"
        return False, ""

    def _has_duplicate_attribute(self) -> bool:
        for entries in (self.ctx.get("attributes") or {}).values():
            seen = set()
            for entry in entries:
                key = (entry.get("attribute"), str(entry.get("value")))
                if key in seen:
                    return True
                seen.add(key)
        return False

    def check_timeout(self) -> bool:
        if self.is_terminal():
            return False
        if self.actions_in_state > self._max_actions:
            self.timeouts += 1
            return True
        return False

    def handle_timeout(self) -> Optional[ExtractionState]:
        if self.is_terminal():
            return None
        if not self.check_timeout():
            return None
        target = STATE_DEFS[self.state]["on_timeout"]
        if target is None:
            return None
        return self.transition_to(target, forced=True)

    def handle_loop(self) -> Optional[ExtractionState]:
        if self.is_terminal():
            return None
        is_loop, reason = self.check_loop()
        if not is_loop:
            return None
        self.loops_prevented += 1
        target = _LOOP_TARGETS.get(self.state)
        if target is None:
            target = STATE_DEFS[self.state]["on_loop"]
        if target is None:
            return None
        return self.transition_to(target, forced=True)

    # ── reporting ────────────────────────────────────────────────────
    def get_prompt(self) -> str:
        if self.state == ExtractionState.START:
            return "Starting extraction. " + self._metrics_suffix()
        if self.state == ExtractionState.COMPLETE:
            return "Extraction complete. " + self._metrics_suffix()
        if self.state == ExtractionState.FAIL:
            return "Extraction failed. " + self._metrics_suffix()
        return f"{STATE_DEFS[self.state]['prompt']} {self._metrics_suffix()}"

    def _metrics_suffix(self) -> str:
        return (f"entities={len(self.ctx.get('entities', []))} "
                f"attributes={self._attribute_count()} "
                f"relations={len(self.ctx.get('relations', []))} "
                f"actions={self.actions_in_state}")

    def _attribute_count(self) -> int:
        return sum(len(entries)
                   for entries in (self.ctx.get("attributes") or {}).values())

    def get_metrics(self) -> Dict[str, Any]:
        validations = self.ctx.get("validation_results", [])
        duplicates_removed = sum(
            1 for item in validations
            if item.get("check") == "check_duplicates" and not item.get("passed"))
        return {
            "efsm_final_state": self.state.value,
            "efsm_entities_found": len(self.ctx.get("entities", [])),
            "efsm_attributes_extracted": self._attribute_count(),
            "efsm_relations_extracted": len(self.ctx.get("relations", [])),
            "efsm_normalizations_applied": len(self.ctx.get("normalizations", [])),
            "efsm_validation_checks": len(validations),
            "efsm_validation_failures_count": self.validation_failures,
            "efsm_duplicates_removed": duplicates_removed,
            "efsm_stored_facts": len(self.ctx.get("stored_facts", [])),
            "efsm_total_actions": self.total_actions,
            "efsm_loops_prevented": self.loops_prevented,
            "efsm_timeouts": self.timeouts,
        }

    # ── serialization ────────────────────────────────────────────────
    def to_context_dict(self) -> Dict[str, Any]:
        return {
            "efsm_state": self.state.value,
            "ctx": self.ctx,
            "history": list(self.history),
            "transitions": list(self.transitions),
            "total_actions": self.total_actions,
            "actions_in_state": self.actions_in_state,
            "consecutive_same_operation": self.consecutive_same_operation,
            "consecutive_same_entity": self.consecutive_same_entity,
            "last_entity_name": self.last_entity_name,
            "last_operation": self.last_operation,
            "validation_failures": self.validation_failures,
            "forced_transitions": self.forced_transitions,
            "loops_prevented": self.loops_prevented,
            "timeouts": self.timeouts,
        }

    @classmethod
    def from_context_dict(cls, data: Dict[str, Any]) -> "ExtractionFSM":
        fsm = cls(ctx=data.get("ctx") or create_extraction_context())
        state_name = str(data.get("efsm_state", "START"))
        try:
            fsm.state = ExtractionState[state_name]
        except KeyError:
            try:
                fsm.state = ExtractionState(state_name)
            except ValueError:
                fsm.state = ExtractionState.START
        fsm.history = list(data.get("history", []))
        fsm.transitions = list(data.get("transitions", []))
        fsm.total_actions = int(data.get("total_actions", 0))
        fsm.actions_in_state = int(data.get("actions_in_state", 0))
        fsm.consecutive_same_operation = int(data.get("consecutive_same_operation", 0))
        fsm.consecutive_same_entity = int(data.get("consecutive_same_entity", 0))
        fsm.last_entity_name = str(data.get("last_entity_name", ""))
        fsm.last_operation = str(data.get("last_operation", ""))
        fsm.validation_failures = int(data.get("validation_failures", 0))
        fsm.forced_transitions = int(data.get("forced_transitions", 0))
        fsm.loops_prevented = int(data.get("loops_prevented", 0))
        fsm.timeouts = int(data.get("timeouts", 0))
        return fsm


__all__ = [
    "ExtractionFSM", "ExtractionState", "STATE_DEFS",
    "create_extraction_context", "normalize_entity_name",
    "normalize_date_value", "normalize_unit", "normalize_price",
    "calculate_claim_similarity", "is_duplicate",
]
