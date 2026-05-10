from jarvis_os.bootstrap import build_jarvis_os


def test_single_execution_path_uses_canonical_components():
    runtime = build_jarvis_os()
    assert runtime.planner.__class__.__module__ == "jarvis_os.core.planner"
    assert runtime.executor.__class__.__module__ == "jarvis_os.core.executor"
    assert runtime.loop.__class__.__module__ == "jarvis_os.core.loop"
