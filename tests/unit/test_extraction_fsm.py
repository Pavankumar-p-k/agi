"""Tests for Research Extraction FSM."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import time
from core.research.extraction_fsm import (
    ExtractionFSM,
    ExtractionState,
    create_extraction_context,
    STATE_DEFS,
    normalize_entity_name,
    normalize_date_value,
    normalize_unit,
    normalize_price,
    calculate_claim_similarity,
    is_duplicate,
    _DUPLICATE_CONFIDENCE_THRESHOLD,
)


def test_initial_state():
    fsm = ExtractionFSM()
    assert fsm.state == ExtractionState.START
    assert not fsm.is_terminal()
    assert len(fsm.ctx["entities"]) == 0


def test_initial_context_empty():
    fsm = ExtractionFSM()
    assert fsm.ctx["source_text"] == ""
    assert fsm.ctx["source_url"] == ""


def test_initial_context_with_source():
    ctx = create_extraction_context(
        source_text="Python 3.13 was released in 2024.",
        source_url="https://docs.python.org",
    )
    fsm = ExtractionFSM(ctx=ctx)
    assert fsm.ctx["source_text"] == "Python 3.13 was released in 2024."
    assert fsm.ctx["source_url"] == "https://docs.python.org"


def test_custom_context():
    ctx = create_extraction_context(source_text="Test content here")
    fsm = ExtractionFSM(ctx=ctx)
    assert fsm.get_prompt()


def test_terminal_states():
    fsm = ExtractionFSM()
    fsm.state = ExtractionState.COMPLETE
    assert fsm.is_terminal()
    fsm.state = ExtractionState.FAIL
    assert fsm.is_terminal()


def test_non_terminal_states():
    for state in ExtractionState:
        if state in (ExtractionState.COMPLETE, ExtractionState.FAIL):
            continue
        fsm = ExtractionFSM()
        fsm.state = state
        assert not fsm.is_terminal(), f"{state.value} should not be terminal"


def test_is_operation_allowed():
    fsm = ExtractionFSM()
    # START only allows initialize/load_document
    assert fsm.is_operation_allowed("initialize")
    assert fsm.is_operation_allowed("load_document")
    assert not fsm.is_operation_allowed("extract_entities")
    assert not fsm.is_operation_allowed("split_entity")


def test_is_operation_allowed_terminal():
    fsm = ExtractionFSM()
    fsm.state = ExtractionState.COMPLETE
    assert not fsm.is_operation_allowed("initialize")


def test_is_operation_allowed_detect():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    assert fsm.is_operation_allowed("extract_entities")
    assert fsm.is_operation_allowed("read_source")
    assert not fsm.is_operation_allowed("split_entity")


def test_is_exit_operation():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    assert fsm.is_exit_operation("extract_entities")
    assert not fsm.is_exit_operation("read_source")


def test_record_action_auto_transition_start():
    fsm = ExtractionFSM()
    assert fsm.state == ExtractionState.START
    fsm.record_action("initialize")
    assert fsm.state == ExtractionState.DETECT_ENTITIES


def test_record_entity():
    fsm = ExtractionFSM()
    fsm.record_entity("Python 3.13", "language_version")
    assert len(fsm.ctx["entities"]) == 1
    assert fsm.ctx["entities"][0]["name"] == "Python 3.13"
    assert fsm.ctx["entities"][0]["type"] == "language_version"


def test_record_entity_tracks_consecutive():
    fsm = ExtractionFSM()
    fsm.record_entity("Python 3.13")
    assert fsm.consecutive_same_entity == 1
    fsm.record_entity("Python 3.13")
    assert fsm.consecutive_same_entity == 2
    fsm.record_entity("Python 3.12")
    assert fsm.consecutive_same_entity == 1


def test_record_entity_different_names():
    fsm = ExtractionFSM()
    fsm.record_entity("Entity A")
    fsm.record_entity("Entity B")
    fsm.record_entity("Entity C")
    assert len(fsm.ctx["entities"]) == 3
    assert fsm.consecutive_same_entity == 1


def test_record_attribute():
    fsm = ExtractionFSM()
    fsm.record_entity("Python 3.13")
    fsm.record_attribute("Python 3.13", "release_year", "2024")
    assert "Python 3.13" in fsm.ctx["attributes"]
    assert len(fsm.ctx["attributes"]["Python 3.13"]) == 1
    assert fsm.ctx["attributes"]["Python 3.13"][0]["attribute"] == "release_year"


def test_record_attribute_multiple():
    fsm = ExtractionFSM()
    fsm.record_entity("Python 3.13")
    fsm.record_attribute("Python 3.13", "release_year", "2024")
    fsm.record_attribute("Python 3.13", "feature", "free-threaded mode")
    assert len(fsm.ctx["attributes"]["Python 3.13"]) == 2


def test_record_relation():
    fsm = ExtractionFSM()
    fsm.record_relation("Python 3.13", "CPython", "implements")
    assert len(fsm.ctx["relations"]) == 1
    assert fsm.ctx["relations"][0]["source"] == "Python 3.13"
    assert fsm.ctx["relations"][0]["type"] == "implements"


def test_record_relation_multiple():
    fsm = ExtractionFSM()
    fsm.record_relation("A", "B", "depends_on")
    fsm.record_relation("B", "C", "extends")
    assert len(fsm.ctx["relations"]) == 2


def test_record_normalization():
    fsm = ExtractionFSM()
    fsm.record_normalization(
        "Python 3.13", "release_year", "2024", "2024-10-01"
    )
    assert len(fsm.ctx["normalizations"]) == 1
    assert fsm.ctx["normalizations"][0]["original"] == "2024"


def test_record_validation_passed():
    fsm = ExtractionFSM()
    fsm.record_validation("check_duplicates", True)
    assert len(fsm.ctx["validation_results"]) == 1
    assert fsm.validation_failures == 0


def test_record_validation_failed():
    fsm = ExtractionFSM()
    fsm.record_validation("check_confidence", False, "confidence below threshold")
    assert fsm.validation_failures == 1
    assert not fsm.ctx["validation_results"][0]["passed"]


def test_record_action_tracks_history():
    fsm = ExtractionFSM()
    fsm.record_action("initialize")
    assert len(fsm.history) == 1
    assert fsm.history[0]["operation"] == "initialize"
    assert fsm.total_actions == 1


def test_record_action_consecutive():
    fsm = ExtractionFSM()
    fsm.record_action("extract_entities")
    fsm.record_action("extract_entities")
    assert fsm.consecutive_same_operation == 2
    fsm.record_action("split_entity")
    assert fsm.consecutive_same_operation == 1


def test_check_loop_same_entity():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    fsm.record_entity("Python 3.13")
    fsm.record_entity("Python 3.13")
    fsm.record_entity("Python 3.13")
    is_loop, reason = fsm.check_loop()
    assert is_loop
    assert "same_entity" in reason


def test_check_loop_no_loop_different_entities():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    fsm.record_entity("Python 3.13")
    fsm.record_entity("Python 3.12")
    fsm.record_entity("Python 3.11")
    assert not fsm.check_loop()[0]


def test_check_loop_same_operation():
    fsm = ExtractionFSM()
    fsm.record_action("extract_entities")
    fsm.record_action("extract_entities")
    fsm.record_action("extract_entities")
    fsm.record_action("extract_entities")
    is_loop, reason = fsm.check_loop()
    assert is_loop
    assert "same_operation" in reason


def test_check_loop_no_entities_detected():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    fsm.record_action("read_source")  # no record_entity calls
    fsm.record_action("read_source")
    fsm.record_action("read_source")
    is_loop, reason = fsm.check_loop()
    assert is_loop
    assert "no_entities" in reason


def test_check_loop_entities_detected_prevents_false_positive():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    fsm.record_action("read_source_0")  # different operations
    fsm.record_action("read_source_1")
    fsm.record_entity("Python 3.13")
    assert not fsm.check_loop()[0]


def test_check_loop_no_attributes():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.EXTRACT_ATTRIBUTES)
    fsm.record_action("read_source_a")
    fsm.record_action("read_source_b")
    fsm.record_action("read_source_c")
    fsm.record_action("read_source_d")
    is_loop, reason = fsm.check_loop()
    assert is_loop
    assert "no_attributes" in reason


def test_check_loop_no_attributes_with_attrs():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.EXTRACT_ATTRIBUTES)
    fsm.record_entity("Entity")
    fsm.record_attribute("Entity", "name", "value")
    fsm.record_action("read_source_a")
    assert not fsm.check_loop()[0]


def test_check_loop_no_relations():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.EXTRACT_RELATIONS)
    fsm.record_action("read_source_a")
    fsm.record_action("read_source_b")
    fsm.record_action("read_source_c")
    fsm.record_action("read_source_d")
    is_loop, reason = fsm.check_loop()
    assert is_loop
    assert "no_relations" in reason


def test_check_loop_no_relations_with_rels():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.EXTRACT_RELATIONS)
    fsm.record_relation("A", "B", "depends")
    fsm.record_action("read_source_a")
    assert not fsm.check_loop()[0]


def test_check_loop_duplicate_attribute():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.EXTRACT_ATTRIBUTES)
    fsm.record_entity("Entity")
    fsm.record_attribute("Entity", "version", "1.0")
    fsm.record_attribute("Entity", "version", "1.0")
    fsm.record_action("extract_attribute")
    fsm.record_action("extract_attribute")
    fsm.record_action("extract_attribute")
    is_loop, reason = fsm.check_loop()
    assert is_loop
    assert "duplicate_attribute" in reason


def test_check_loop_no_false_positive():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    fsm.record_entity("Python 3.13")
    fsm.record_action("extract_entities")
    assert not fsm.check_loop()[0]


def test_check_timeout():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    for _ in range(4):  # max_actions=3
        fsm.record_action("read_source")
    assert fsm.check_timeout()
    assert fsm.timeouts == 1


def test_check_timeout_terminal():
    fsm = ExtractionFSM()
    fsm.state = ExtractionState.COMPLETE
    assert not fsm.check_timeout()


def test_check_timeout_not_reached():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    fsm.record_action("read_source")
    assert not fsm.check_timeout()


def test_transition_to():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    assert fsm.state == ExtractionState.DETECT_ENTITIES
    assert fsm.actions_in_state == 0
    assert len(fsm.transitions) == 1
    assert fsm.transitions[0]["from"] == ExtractionState.START.value
    assert fsm.transitions[0]["to"] == ExtractionState.DETECT_ENTITIES.value
    assert not fsm.transitions[0]["forced"]


def test_transition_to_forced():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES, forced=True)
    assert fsm.forced_transitions == 1
    assert fsm.transitions[0]["forced"]


def test_transition_to_self():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.START)
    assert len(fsm.transitions) == 0


def test_handle_exit_operation():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    result = fsm.handle_exit_operation("extract_entities")
    assert result == ExtractionState.SPLIT_ENTITIES
    assert fsm.state == ExtractionState.SPLIT_ENTITIES


def test_handle_exit_operation_no_match():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    result = fsm.handle_exit_operation("read_source")
    assert result is None


def test_handle_timeout():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.NORMALIZE)
    for _ in range(7):  # max_actions=6
        fsm.record_action("normalize_name")
    result = fsm.handle_timeout()
    assert result == ExtractionState.VALIDATE  # NORMALIZE on_timeout -> VALIDATE
    assert fsm.forced_transitions > 0


def test_handle_timeout_terminal():
    fsm = ExtractionFSM()
    fsm.state = ExtractionState.COMPLETE
    assert fsm.handle_timeout() is None


def test_handle_loop_detect_entities():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    fsm.record_entity("Same")
    fsm.record_entity("Same")
    fsm.record_entity("Same")
    result = fsm.handle_loop()
    assert result == ExtractionState.SPLIT_ENTITIES
    assert fsm.loops_prevented > 0


def test_handle_loop_extract_attributes():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.EXTRACT_ATTRIBUTES)
    fsm.last_entity_name = "Entity"
    fsm.consecutive_same_entity = 3
    result = fsm.handle_loop()
    assert result == ExtractionState.EXTRACT_RELATIONS


def test_handle_loop_extract_relations():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.EXTRACT_RELATIONS)
    fsm.last_entity_name = "Entity"
    fsm.consecutive_same_entity = 3
    result = fsm.handle_loop()
    assert result == ExtractionState.NORMALIZE


def test_handle_loop_validate():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.VALIDATE)
    fsm.consecutive_same_entity = 3
    result = fsm.handle_loop()
    assert result == ExtractionState.STORE
    assert fsm.state == ExtractionState.STORE


def test_handle_loop_normalize():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.NORMALIZE)
    fsm.consecutive_same_entity = 3
    result = fsm.handle_loop()
    assert result == ExtractionState.VALIDATE
    assert fsm.state == ExtractionState.VALIDATE


def test_handle_loop_no_loop():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    fsm.record_entity("Python 3.13")
    result = fsm.handle_loop()
    assert result is None


def test_handle_loop_not_triggered():
    fsm = ExtractionFSM()
    assert fsm.handle_loop() is None


def test_get_prompt_start():
    fsm = ExtractionFSM()
    prompt = fsm.get_prompt()
    assert "Starting" in prompt


def test_get_prompt_with_metrics():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    fsm.record_entity("Entity A")
    prompt = fsm.get_prompt()
    assert "entities=1" in prompt


def test_get_prompt_complete():
    fsm = ExtractionFSM()
    fsm.state = ExtractionState.COMPLETE
    prompt = fsm.get_prompt()
    assert "complete" in prompt.lower()


def test_get_prompt_fail():
    fsm = ExtractionFSM()
    fsm.state = ExtractionState.FAIL
    prompt = fsm.get_prompt()
    assert "failed" in prompt.lower()


def test_get_metrics():
    fsm = ExtractionFSM(ctx=create_extraction_context(
        source_text="Python 3.13 was released in 2024.",
        source_url="https://docs.python.org",
    ))
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    fsm.record_entity("Python 3.13", "language_version")
    fsm.record_entity("CPython", "runtime")
    fsm.record_attribute("Python 3.13", "release_year", "2024")
    fsm.record_relation("Python 3.13", "CPython", "runs_on")
    fsm.record_normalization("Python 3.13", "name", "python 3.13", "Python 3.13")

    metrics = fsm.get_metrics()
    assert metrics["efsm_final_state"] == ExtractionState.DETECT_ENTITIES.value
    assert metrics["efsm_entities_found"] == 2
    assert metrics["efsm_attributes_extracted"] == 1
    assert metrics["efsm_relations_extracted"] == 1
    assert metrics["efsm_normalizations_applied"] == 1


def test_get_metrics_empty():
    fsm = ExtractionFSM()
    metrics = fsm.get_metrics()
    assert metrics["efsm_entities_found"] == 0
    assert metrics["efsm_attributes_extracted"] == 0
    assert metrics["efsm_validation_checks"] == 0


def test_forced_transition_increments():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES, forced=True)
    fsm.transition_to(ExtractionState.SPLIT_ENTITIES, forced=True)
    assert fsm.forced_transitions == 2


def test_loops_prevented_increments():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    fsm.record_entity("Same")
    fsm.record_entity("Same")
    fsm.record_entity("Same")
    fsm.handle_loop()
    assert fsm.loops_prevented >= 1


def test_timeouts_increments():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    for _ in range(4):
        fsm.record_action("read_source")
    assert fsm.check_timeout()
    assert fsm.timeouts == 1


def test_validation_failures_count():
    fsm = ExtractionFSM()
    fsm.record_validation("check", False)
    fsm.record_validation("check", True)
    fsm.record_validation("check", False)
    assert fsm.validation_failures == 2


def test_to_from_context_dict_roundtrip():
    fsm = ExtractionFSM(ctx=create_extraction_context(
        source_text="Test document",
        source_url="https://example.com",
    ))
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    fsm.record_entity("Entity A")
    fsm.record_entity("Entity B")
    fsm.record_attribute("Entity A", "version", "1.0")

    data = fsm.to_context_dict()
    restored = ExtractionFSM.from_context_dict(data)

    assert restored.state == fsm.state
    assert restored.ctx["source_text"] == "Test document"
    assert len(restored.ctx["entities"]) == 2
    assert restored.total_actions == fsm.total_actions


def test_from_context_dict_minimal():
    data = {"efsm_state": "START", "ctx": create_extraction_context()}
    restored = ExtractionFSM.from_context_dict(data)
    assert restored.state == ExtractionState.START
    assert restored.total_actions == 0


def test_state_defs_consistent():
    for state in ExtractionState:
        assert state in STATE_DEFS, f"Missing definition for {state}"
        defn = STATE_DEFS[state]
        assert "allowed_operations" in defn
        assert "exit_operations" in defn
        assert "max_actions" in defn
        assert "on_exit" in defn
        assert "on_timeout" in defn
        assert "prompt" in defn


def test_normalize_entity_name_basic():
    assert normalize_entity_name("  Python 3.13  ") == "Python 3.13"


def test_normalize_entity_name_article():
    assert normalize_entity_name("The Python Language") == "Python Language"
    assert normalize_entity_name("A FastAPI Framework") == "FastAPI Framework"


def test_normalize_entity_name_punctuation():
    assert normalize_entity_name("Python 3.13,") == "Python 3.13"
    assert normalize_entity_name("Hello World!") == "Hello World"


def test_normalize_entity_name_whitespace():
    assert normalize_entity_name("Python   3.13") == "Python 3.13"


def test_normalize_entity_name_empty():
    assert normalize_entity_name("") == ""


def test_normalize_date_iso():
    assert normalize_date_value("2024-10-01") == "2024-10-01"


def test_normalize_date_text():
    result = normalize_date_value("October 1, 2024")
    assert result == "2024-10-01"


def test_normalize_date_text_reverse():
    result = normalize_date_value("1 October 2024")
    assert result == "2024-10-01"


def test_normalize_date_month_abbr():
    result = normalize_date_value("Jan 15, 2023")
    assert result == "2023-01-15"


def test_normalize_date_year_only():
    assert normalize_date_value("2024") == "2024"


def test_normalize_date_invalid():
    assert normalize_date_value("not a date") == "not a date"


def test_normalize_unit_kb():
    result = normalize_unit("1024 kilobytes")
    assert "KB" in result


def test_normalize_unit_mb():
    result = normalize_unit("512 megabytes")
    assert "MB" in result


def test_normalize_unit_gb():
    result = normalize_unit("16 gigabytes")
    assert "GB" in result


def test_normalize_unit_ms():
    result = normalize_unit("200 milliseconds")
    assert "ms" in result


def test_normalize_unit_km():
    result = normalize_unit("10 kilometers")
    assert "km" in result


def test_normalize_unit_no_match():
    assert normalize_unit("100 units") == "100 units"


def test_normalize_price_simple():
    assert normalize_price("$99") == "$99.00"


def test_normalize_price_with_cents():
    assert normalize_price("$99.99") == "$99.99"


def test_normalize_price_thousands():
    assert normalize_price("$1,500") == "$1500.00"


def test_normalize_price_no_dollar():
    assert normalize_price("99") == "$99.00"


def test_normalize_price_no_match():
    assert normalize_price("free") == "free"


def test_calculate_claim_similarity_identical():
    assert calculate_claim_similarity("Python 3.13 was released", "Python 3.13 was released") == 1.0


def test_calculate_claim_similarity_partial():
    sim = calculate_claim_similarity(
        "Python 3.13 was released in 2024",
        "Python 3.13 was released"
    )
    assert 0.7 < sim < 1.0


def test_calculate_claim_similarity_no_overlap():
    assert calculate_claim_similarity("Python 3.13", "Coffee brewing") == 0.0


def test_calculate_claim_similarity_empty():
    assert calculate_claim_similarity("", "something") == 0.0
    assert calculate_claim_similarity("something", "") == 0.0


def test_is_duplicate_identical():
    assert is_duplicate(
        ["Python 3.13 was released in 2024"],
        "Python 3.13 was released in 2024"
    )


def test_is_duplicate_similar():
    assert is_duplicate(
        ["Python 3.13 released in 2024"],
        "Python 3.13 was released in 2024"
    )


def test_is_duplicate_not():
    assert not is_duplicate(
        ["Python is a programming language"],
        "Python 3.13 was released in 2024"
    )


def test_is_duplicate_empty_list():
    assert not is_duplicate([], "Python 3.13 was released in 2024")


def test_metric_duplicates_removed():
    fsm = ExtractionFSM()
    fsm.record_validation("check_duplicates", True)
    fsm.record_validation("check_duplicates", False)
    metrics = fsm.get_metrics()
    assert metrics["efsm_duplicates_removed"] == 1


def test_metric_validation_checks_count():
    fsm = ExtractionFSM()
    fsm.record_validation("check_duplicates", True)
    fsm.record_validation("check_confidence", False)
    fsm.record_validation("check_citations", True)
    metrics = fsm.get_metrics()
    assert metrics["efsm_validation_checks"] == 3
    assert metrics["efsm_validation_failures_count"] == 1


def test_metric_stored_facts():
    fsm = ExtractionFSM()
    fsm.ctx["stored_facts"] = ["fact_001", "fact_002"]
    metrics = fsm.get_metrics()
    assert metrics["efsm_stored_facts"] == 2


def test_full_extraction_flow():
    """End-to-end flow through all states."""
    ctx = create_extraction_context(
        source_text="Python 3.13 was released in October 2024. "
                    "It features free-threaded mode and an experimental JIT compiler.",
        source_url="https://docs.python.org/3/whatsnew/3.13.html",
    )
    fsm = ExtractionFSM(ctx=ctx)

    # START
    assert fsm.state == ExtractionState.START
    fsm.record_action("initialize")
    assert fsm.state == ExtractionState.DETECT_ENTITIES

    # DETECT_ENTITIES
    fsm.record_entity("Python 3.13", "language_version")
    fsm.handle_exit_operation("extract_entities")
    assert fsm.state == ExtractionState.SPLIT_ENTITIES

    # SPLIT_ENTITIES — no splitting needed in this case
    fsm.handle_exit_operation("split_entity")
    assert fsm.state == ExtractionState.EXTRACT_ATTRIBUTES

    # EXTRACT_ATTRIBUTES
    fsm.record_attribute("Python 3.13", "release_date", "October 2024")
    fsm.record_attribute("Python 3.13", "feature", "free-threaded mode")
    fsm.record_attribute("Python 3.13", "feature", "experimental JIT compiler")
    fsm.handle_exit_operation("extract_attribute")
    assert fsm.state == ExtractionState.EXTRACT_RELATIONS

    # EXTRACT_RELATIONS
    fsm.record_relation("Python 3.13", "CPython", "implements")
    fsm.handle_exit_operation("extract_relation")
    assert fsm.state == ExtractionState.NORMALIZE

    # NORMALIZE
    fsm.record_normalization("Python 3.13", "release_date", "October 2024", "2024-10-01")
    fsm.handle_exit_operation("normalize_name")
    assert fsm.state == ExtractionState.VALIDATE

    # VALIDATE
    fsm.record_validation("check_duplicates", True)
    fsm.record_validation("check_confidence", True)
    fsm.handle_exit_operation("check_duplicates")
    assert fsm.state == ExtractionState.STORE

    # STORE
    fsm.ctx["stored_facts"] = ["fact_001", "fact_002", "fact_003"]
    fsm.handle_exit_operation("persist_facts")
    assert fsm.state == ExtractionState.COMPLETE
    assert fsm.is_terminal()


def test_full_flow_with_loop_detection():
    """Flow where loop detection forces advancement."""
    ctx = create_extraction_context(
        source_text="Entity A is related to Entity B.",
        source_url="https://example.com",
    )
    fsm = ExtractionFSM(ctx=ctx)
    fsm.record_action("initialize")
    assert fsm.state == ExtractionState.DETECT_ENTITIES

    # Extract same entity repeatedly to trigger loop
    fsm.record_entity("Same Entity")
    fsm.record_entity("Same Entity")
    fsm.record_entity("Same Entity")
    result = fsm.handle_loop()
    assert result == ExtractionState.SPLIT_ENTITIES
    assert fsm.forced_transitions >= 1


def test_full_flow_no_entities():
    """When no entities found, loop detection advances to SPLIT."""
    fsm = ExtractionFSM()
    fsm.record_action("initialize")
    assert fsm.state == ExtractionState.DETECT_ENTITIES
    fsm.record_action("read_source")
    fsm.record_action("read_source")
    fsm.record_action("read_source")
    result = fsm.handle_loop()
    # Should advance to SPLIT even with no entities
    assert result == ExtractionState.SPLIT_ENTITIES


def test_full_flow_no_attributes():
    """When no attributes found, loop detection advances to relations."""
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.EXTRACT_ATTRIBUTES)
    fsm.record_entity("Entity")
    fsm.record_action("read_source_a")
    fsm.record_action("read_source_b")
    fsm.record_action("read_source_c")
    fsm.record_action("read_source_d")
    result = fsm.handle_loop()
    assert result == ExtractionState.EXTRACT_RELATIONS


def test_serialization_preserves_entities():
    ctx = create_extraction_context(source_text="Test")
    fsm = ExtractionFSM(ctx=ctx)
    fsm.record_entity("Entity A")
    fsm.record_entity("Entity B")

    data = fsm.to_context_dict()
    restored = ExtractionFSM.from_context_dict(data)

    assert len(restored.ctx["entities"]) == 2
    assert restored.ctx["entities"][0]["name"] == "Entity A"


def test_serialization_preserves_attributes():
    ctx = create_extraction_context(source_text="Test")
    fsm = ExtractionFSM(ctx=ctx)
    fsm.record_entity("E")
    fsm.record_attribute("E", "attr", "val")

    data = fsm.to_context_dict()
    restored = ExtractionFSM.from_context_dict(data)

    assert restored.ctx["attributes"]["E"][0]["attribute"] == "attr"
    assert restored.ctx["attributes"]["E"][0]["value"] == "val"


def test_serialization_preserves_relations():
    ctx = create_extraction_context(source_text="Test")
    fsm = ExtractionFSM(ctx=ctx)
    fsm.record_relation("A", "B", "link")

    data = fsm.to_context_dict()
    restored = ExtractionFSM.from_context_dict(data)
    assert len(restored.ctx["relations"]) == 1


def test_serialization_preserves_state():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.VALIDATE)
    fsm.record_validation("check", False)

    data = fsm.to_context_dict()
    restored = ExtractionFSM.from_context_dict(data)
    assert restored.state == ExtractionState.VALIDATE
    assert restored.validation_failures == 1


def test_serialization_preserves_transitions():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.DETECT_ENTITIES)
    fsm.transition_to(ExtractionState.SPLIT_ENTITIES)

    data = fsm.to_context_dict()
    restored = ExtractionFSM.from_context_dict(data)

    assert len(restored.transitions) == 2


def test_resume_after_interruption():
    """Simulate crash and resume from serialized state."""
    ctx = create_extraction_context(
        source_text="Original source text",
        source_url="https://example.com/doc",
    )
    fsm = ExtractionFSM(ctx=ctx)
    fsm.record_action("initialize")
    fsm.record_entity("Entity A")
    fsm.record_entity("Entity B")
    fsm.record_attribute("Entity A", "version", "2.0")

    # Simulate crash: serialize
    data = fsm.to_context_dict()

    # Simulate resume: deserialize into new FSM
    restored = ExtractionFSM.from_context_dict(data)

    # Continue extraction from where we left off
    assert restored.state == ExtractionState.DETECT_ENTITIES
    assert len(restored.ctx["entities"]) == 2
    assert restored.ctx["attributes"]["Entity A"][0]["value"] == "2.0"
    assert restored.ctx["source_text"] == "Original source text"
    assert restored.ctx["source_url"] == "https://example.com/doc"


def test_resume_and_continue():
    """Resume from interrupted state and continue the flow."""
    ctx = create_extraction_context(source_text="Test content")
    fsm = ExtractionFSM(ctx=ctx)
    fsm.record_action("initialize")
    fsm.record_entity("Entity A")
    data = fsm.to_context_dict()

    restored = ExtractionFSM.from_context_dict(data)
    # Continue
    restored.record_entity("Entity B")
    restored.record_attribute("Entity A", "name", "Test Entity")
    restored.handle_exit_operation("extract_entities")

    assert restored.state == ExtractionState.SPLIT_ENTITIES
    assert len(restored.ctx["entities"]) == 2


def test_empty_extraction_context():
    fsm = ExtractionFSM()
    assert fsm.state == ExtractionState.START
    assert fsm.ctx["source_text"] == ""
    assert len(fsm.ctx["entities"]) == 0


def test_error_no_false_loops():
    fsm = ExtractionFSM()
    fsm.transition_to(ExtractionState.EXTRACT_ATTRIBUTES)
    fsm.record_entity("E1")
    fsm.record_attribute("E1", "a", "1")
    fsm.record_entity("E2")
    fsm.record_attribute("E2", "b", "2")
    fsm.record_action("extract_attribute_1")
    fsm.record_action("extract_attribute_2")
    assert not fsm.check_loop()[0]


def test_multiple_metrics_accumulate():
    fsm = ExtractionFSM()
    for i in range(3):
        fsm.record_entity(f"E{i}")
    fsm.record_attribute("E0", "v", "1")
    fsm.record_attribute("E0", "v2", "2")
    fsm.record_relation("E0", "E1", "link")
    fsm.record_normalization("E0", "name", "e0", "E0")
    fsm.record_validation("dup", True)
    fsm.record_validation("conf", False)

    m = fsm.get_metrics()
    assert m["efsm_entities_found"] == 3
    assert m["efsm_attributes_extracted"] == 2
    assert m["efsm_relations_extracted"] == 1
    assert m["efsm_normalizations_applied"] == 1
    assert m["efsm_validation_checks"] == 2
    assert m["efsm_validation_failures_count"] == 1


def test_state_prompt_for_each_state():
    """Every state should have a non-empty prompt."""
    for state in ExtractionState:
        defn = STATE_DEFS[state]
        assert defn["prompt"], f"Empty prompt for {state.value}"
