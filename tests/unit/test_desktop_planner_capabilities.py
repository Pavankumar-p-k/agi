import jarvis_desktop_agent as agent


def test_planner_capability_context_exposes_registered_boundaries():
    context = agent._capability_context_for_prompt()
    assert "[DESKTOP CAPABILITIES]" in context
    assert "registered_adapters" in context
    assert "supported_profile_count" in context


def test_planner_capability_context_does_not_claim_unknown_apps():
    context = agent._capability_context_for_prompt()
    assert "Do not claim an app-specific capability" in context
