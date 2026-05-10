#!/usr/bin/env python3
"""
Validation script for JARVIS OS cognitive agent brain upgrade.
Tests all critical components to ensure system is functioning correctly.
"""

from __future__ import annotations

import json
import sys
from typing import Any

# Test 1: Intent Engine
def test_intent_engine(registry_mock: Any) -> bool:
    """Verify intent passthrough works."""
    print("✓ Test 1: Intent Engine (Goal Passthrough)")
    try:
        from jarvis_os.core.intent import IntentEngine
        
        engine = IntentEngine(registry_mock)
        result = engine.parse("Build a feature for user authentication")
        
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert result["goal"] == "Build a feature for user authentication"
        assert result["type"] == "auto"
        print("  ✓ Returns correct dict format")
        print(f"  ✓ Output: {result}")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return False


# Test 2: Planner with JSON validation
def test_planner_json_output(models_mock: Any, registry_mock: Any) -> bool:
    """Verify planner generates valid JSON DAG."""
    print("✓ Test 2: Planner (LLM DAG Generation)")
    try:
        from jarvis_os.core.planner import PlanningEngine
        
        # Mock models.generate to return valid JSON
        models_mock.generate = lambda task, prompt: json.dumps({
            "tasks": [
                {"id": "t1", "tool": "list_files", "args": {"path": "."}, "deps": [], "success": ""},
                {"id": "t2", "tool": "read_file", "args": {"path": "main.py"}, "deps": ["t1"], "success": ""}
            ]
        })
        
        planner = PlanningEngine(registry_mock, models_mock)
        intent = {"goal": "Analyze main.py", "type": "auto"}
        analysis = {"recommended_tools": [{"name": "list_files"}, {"name": "read_file"}]}
        
        plan = planner.build_plan("Analyze main.py", intent, analysis)
        
        assert plan is not None, "Plan is None"
        assert len(plan.steps) >= 1, f"Expected steps in plan, got {len(plan.steps)}"
        assert plan.strategy == "llm_dag", f"Expected llm_dag strategy, got {plan.strategy}"
        print("  ✓ Plan generated successfully")
        print(f"  ✓ Steps: {len(plan.steps)}")
        print(f"  ✓ Strategy: {plan.strategy}")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


# Test 3: Critic Engine
def test_critic_engine(models_mock: Any) -> bool:
    """Verify critic generates structured evaluation."""
    print("✓ Test 3: Critic Engine (Structured Evaluation)")
    try:
        from jarvis_os.core.critic import CriticEngine
        
        # Mock models.generate to return valid critic JSON
        models_mock.generate = lambda task, prompt: json.dumps({
            "score": 0.85,
            "failure_type": "",
            "issues": [],
            "fix_strategy": "",
            "replan": False
        })
        
        critic = CriticEngine(models_mock)
        plan_dict = {"goal": "test", "steps": []}
        
        from jarvis_os.contracts import ExecutionReport
        execution = ExecutionReport(goal="test", plan_id="p1", success=True)
        execution.results = []
        
        result = critic.evaluate("Test goal", plan_dict, execution)
        
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert "score" in result, "Missing 'score' in result"
        assert "failure_type" in result, "Missing 'failure_type' in result"
        assert "replan" in result, "Missing 'replan' in result"
        assert 0.0 <= result["score"] <= 1.0, f"Score out of range: {result['score']}"
        print("  ✓ Evaluation generated successfully")
        print(f"  ✓ Score: {result['score']}")
        print(f"  ✓ Replan: {result['replan']}")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


# Test 4: Meta Controller
def test_meta_controller() -> bool:
    """Verify meta controller makes correct decisions."""
    print("✓ Test 4: Meta-Controller (Decision Making)")
    try:
        from jarvis_os.core.meta_controller import MetaController
        
        meta = MetaController(max_iterations=5)
        
        # Test 1: Stop at success
        decision = meta.decide(1, {"score": 0.95, "replan": False})
        assert decision["action"] == "stop", f"Expected 'stop', got {decision['action']}"
        print("  ✓ Stops on high score (0.95)")
        
        # Test 2: Replan on low score
        decision = meta.decide(1, {"score": 0.5, "replan": True})
        assert decision["action"] == "replan", f"Expected 'replan', got {decision['action']}"
        print("  ✓ Replans on low score with replan=True")
        
        # Test 3: Stop at max iterations
        decision = meta.decide(5, {"score": 0.5, "replan": True})
        assert decision["action"] == "stop", f"Expected 'stop' at max, got {decision['action']}"
        print("  ✓ Stops at max iterations")
        
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return False


# Test 5: Tool Registry Normalization
def test_tool_registry_normalization() -> bool:
    """Verify tool outputs are normalized."""
    print("✓ Test 5: Tool Registry (Output Normalization)")
    try:
        from jarvis_os.tools.tool_registry import ToolRegistry
        from jarvis_os.contracts import ToolSpec
        
        # Create registry with mocks
        config_mock = type('Config', (), {})()
        memory_mock = type('Memory', (), {})()
        models_mock = type('Models', (), {})()
        
        registry = ToolRegistry(config=config_mock, memory=memory_mock, models=models_mock)
        
        # Register a simple tool
        spec = ToolSpec(
            name="test_tool",
            description="Test tool",
            arguments=[],
            parameters={}
        )
        
        def test_handler(**kwargs):
            return {"message": "hello"}
        
        registry.register(spec, test_handler)
        
        # Invoke and check normalization
        result = registry.invoke("test_tool")
        assert result["status"] == "success", f"Expected status=success, got {result.get('status')}"
        assert "data" in result, "Missing 'data' key in normalized output"
        print("  ✓ Output normalized to standard format")
        print(f"  ✓ Result: {result}")
        
        # Test error handling
        result = registry.invoke("nonexistent_tool")
        assert result["status"] == "error", f"Expected status=error, got {result.get('status')}"
        assert "error" in result, "Missing 'error' key"
        print("  ✓ Errors properly structured")
        
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


# Test 6: Vector Store Persistence
def test_vector_store_persistence() -> bool:
    """Verify memory persistence works."""
    print("✓ Test 6: Vector Store (Persistence)")
    try:
        import os
        import tempfile
        from jarvis_os.memory.vector_store import VectorStore
        
        # Use temp file
        temp_dir = tempfile.gettempdir()
        persist_path = os.path.join(temp_dir, "test_vector_store.json")
        
        # Create and populate
        store1 = VectorStore(persist_path=persist_path)
        store1.add({"text": "test document", "kind": "test", "metadata": {}})
        
        # Reload and verify
        store2 = VectorStore(persist_path=persist_path)
        results = store2.search("test", top_k=5)
        assert len(results) > 0, "Document not persisted"
        print("  ✓ Documents persisted to disk")
        print(f"  ✓ Retrieved {len(results)} documents")
        
        # Cleanup
        if os.path.exists(persist_path):
            os.remove(persist_path)
        
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return False


# Test 7: Agent Loop Cycle
def test_agent_loop() -> bool:
    """Verify main agent loop executes."""
    print("✓ Test 7: Agent Loop (Plan-Execute-Evaluate Cycle)")
    try:
        from jarvis_os.core.loop import AgentLoop
        from jarvis_os.core.critic import CriticEngine
        from jarvis_os.core.meta_controller import MetaController
        from jarvis_os.contracts import ExecutionReport, LoopTrace
        
        # Create mocks
        intent_engine = type('IE', (), {
            'parse': lambda self, p: {"goal": p, "type": "auto"}
        })()
        
        planner = type('Planner', (), {
            'build_plan': lambda self, p, i, a: type('Plan', (), {
                'plan_id': 'p1',
                'steps': [],
                'to_dict': lambda: {"goal": p, "steps": []}
            })()
        })()
        
        executor = type('Executor', (), {
            'execute': lambda self, p, **kw: ExecutionReport(goal="test", plan_id="p1", success=True)
        })()
        
        models = type('Models', (), {})()
        models.generate = lambda t, p: json.dumps({"score": 0.9, "replan": False})
        
        critic = CriticEngine(models)
        meta = MetaController(max_iterations=2)
        
        # Create loop
        loop = AgentLoop(
            intent_engine=intent_engine,
            planner=planner,
            executor=executor,
            critic=critic,
            meta_controller=meta
        )
        
        # Run loop
        result = loop.run(prompt="Test", context={})
        
        assert "trace" in result, "Missing trace in result"
        assert "final_execution" in result, "Missing execution in result"
        print("  ✓ Loop executed successfully")
        print(f"  ✓ Trace: {len(result['trace']['cycles'])} cycles")
        
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main() -> int:
    """Run all validation tests."""
    print("\n" + "="*60)
    print("JARVIS OS Cognitive Agent Brain - Validation Suite")
    print("="*60 + "\n")
    
    # Create mocks
    class MockRegistry:
        def recommend(self, prompt, intent):
            return []
    
    class MockModels:
        def generate(self, task, prompt):
            return json.dumps({})
    
    registry_mock = MockRegistry()
    models_mock = MockModels()
    
    tests = [
        ("Intent Engine", lambda: test_intent_engine(registry_mock)),
        ("Planner", lambda: test_planner_json_output(models_mock, registry_mock)),
        ("Critic Engine", lambda: test_critic_engine(models_mock)),
        ("Meta-Controller", test_meta_controller),
        ("Tool Registry", test_tool_registry_normalization),
        ("Vector Store", test_vector_store_persistence),
        ("Agent Loop", test_agent_loop),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n✗ Test '{name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
        print()
    
    # Summary
    print("="*60)
    print("VALIDATION SUMMARY")
    print("="*60)
    passed = sum(1 for _, p in results if p)
    total = len(results)
    for name, passed_flag in results:
        status = "✓ PASS" if passed_flag else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    print("="*60 + "\n")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
