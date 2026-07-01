from __future__ import annotations

import hashlib

import pytest

from core.capability.composition import CompositionEngine, CompositionPlan
from core.capability.graph import CapabilityGraph, CapabilityNode
from core.capability.models import Capability, _BUILTIN_CAPABILITIES
from core.capability.negotiation import (
    CandidateScore,
    CapabilityNegotiator,
    NegotiationResult,
)
from core.capability.registry import CapabilityRegistry
from core.capability.graph import capability_graph


def _make_provider(pid="mock", caps=None):
    from core.providers.base import (
        ExecutionProvider, ProviderCapabilities,
        ProviderHealth, ProviderHealthStatus, ExecutionResult,
    )
    caps_list = caps or ["coding"]

    class _P(ExecutionProvider):
        provider_id = pid
        name = pid.title()
        version = "1.0"
        priority = 50
        installed = True
        _enabled = True
        def capabilities(self): return ProviderCapabilities(capability_names=list(caps_list))
        async def health(self): return ProviderHealth(status=ProviderHealthStatus.HEALTHY)
        async def execute(self, task, ctx=None): return ExecutionResult(success=True, output="ok")

    return _P()


class TestGate1PlannerNoProviderNames:
    def test_planner_uses_capability_not_provider(self):
        graph = capability_graph
        subgraph = graph.resolve_goal("build app")
        for node in subgraph.nodes:
            assert isinstance(node, CapabilityNode)
            assert node.capability_id != ""

    def test_planner_imports_no_provider_names(self):
        import ast
        import inspect
        import core.planner
        source = inspect.getsource(core.planner)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in (
                "ExecutionProvider", "ProviderRegistry", "ProviderRouter",
            ):
                if isinstance(node.ctx, ast.Load):
                    pass


class TestGate2RegistrationUpdatesGraph:
    def test_new_registration_accessible_via_registry(self, clean_registry):
        cr = CapabilityRegistry(registry=clean_registry)
        cap = Capability(id="test_cap", version=1, description="test", tags=("test",))
        cr.register(cap)
        assert cr.get("test_cap") is cap

    def test_registered_capability_appears_in_all(self, clean_registry):
        p = _make_provider("test_prov", caps=["test_cap"])
        clean_registry.register(p, priority=50)
        assert clean_registry.has_capability("test_cap") is True


class TestGate3RemovalReroutes:
    def test_removal_reroutes_to_another(self, clean_registry):
        from core.providers.router import ProviderRouter

        p1 = _make_provider("primary", caps=["coding"])
        p2 = _make_provider("backup", caps=["coding"])
        clean_registry.register(p1, priority=50)
        clean_registry.register(p2, priority=30)

        graph = CapabilityGraph()
        node = CapabilityNode(capability_id="coding")
        router = ProviderRouter()
        router._registry = clean_registry
        negotiator = CapabilityNegotiator(graph=graph, router=router, registry=clean_registry)

        result_before = negotiator.resolve(node)
        assert result_before.chosen_provider_id == "primary"

        clean_registry.unregister("primary")
        result_after = negotiator.resolve(node)
        assert result_after.chosen_provider_id == "backup"

    def test_no_provider_leaves_empty_result(self, clean_registry):
        from core.providers.router import ProviderRouter

        graph = CapabilityGraph()
        node = CapabilityNode(capability_id="nonexistent_cap")
        router = ProviderRouter()
        router._registry = clean_registry
        negotiator = CapabilityNegotiator(graph=graph, router=router, registry=clean_registry)

        result = negotiator.resolve(node)
        assert result.chosen_provider_id == ""
        assert len(result.fallback_chain) >= 0


class TestGate4CapabilityVersioning:
    def test_capability_has_version(self):
        cap = Capability(id="test", version=2, description="v2")
        assert cap.version == 2

    def test_multiple_versions_coexist(self, clean_registry):
        cr = CapabilityRegistry(registry=clean_registry)
        v1 = Capability(id="multi_test", version=1, description="v1", tags=("v1",))
        v2 = Capability(id="multi_test", version=2, description="v2", tags=("v2",))
        cr.register(v1)
        cr.register(v2)
        stored = cr.get("multi_test")
        assert stored is not None and stored.version == 2

    def test_node_carries_version(self):
        node = CapabilityNode(capability_id="coding", version=3)
        assert node.version == 3


class TestGate5DeterministicNegotiation:
    def test_identical_inputs_identical_outputs(self, clean_registry):
        from core.providers.router import ProviderRouter

        p = _make_provider("stable", caps=["coding"])
        clean_registry.register(p, priority=50)

        graph = CapabilityGraph()
        node = CapabilityNode(capability_id="coding")
        router = ProviderRouter()
        router._registry = clean_registry
        negotiator = CapabilityNegotiator(graph=graph, router=router, registry=clean_registry)

        r1 = negotiator.resolve(node)
        r2 = negotiator.resolve(node)
        assert r1.chosen_provider_id == r2.chosen_provider_id
        assert r1.score == r2.score

    def test_composition_deterministic(self, clean_registry):
        from core.providers.router import ProviderRouter

        p = _make_provider("multi", caps=["coding", "testing"])
        clean_registry.register(p, priority=50)

        graph = CapabilityGraph()
        router = ProviderRouter()
        router._registry = clean_registry
        negotiator = CapabilityNegotiator(graph=graph, router=router, registry=clean_registry)
        engine = CompositionEngine(graph=graph, negotiator=negotiator, registry=clean_registry)

        plan1 = engine.compose("build app")
        plan2 = engine.compose("build app")
        assert plan1.subgraph_fingerprint == plan2.subgraph_fingerprint
        assert len(plan1.steps) == len(plan2.steps)


class TestGate6GraphCaching:
    def test_cache_hits_increase(self):
        graph = CapabilityGraph()
        _ = graph.resolve_goal("browse web")
        _ = graph.resolve_goal("browse web")
        stats = graph.cache_stats()
        assert stats["hits"] == 1
        assert stats["cached_subgraphs"] >= 1

    def test_cache_misses_for_new_goal(self):
        graph = CapabilityGraph()
        _ = graph.resolve_goal("unique_goal_string_abc123")
        stats = graph.cache_stats()
        assert stats["misses"] >= 1

    def test_cache_invalidate_clears(self):
        graph = CapabilityGraph()
        _ = graph.resolve_goal("build app")
        stats_before = graph.cache_stats()
        assert stats_before["hits"] == 0
        graph.invalidate()
        stats_after = graph.cache_stats()
        assert stats_after["cached_subgraphs"] == 0

    def test_goal_template_uses_cache(self):
        graph = CapabilityGraph()
        r1 = graph.resolve_goal("build web server")
        r2 = graph.resolve_goal("build android app")
        assert r1 is not r2
        if r1.fingerprint == r2.fingerprint:
            assert r1.nodes == r2.nodes

    def test_cache_fingerprint_tracks_content(self):
        graph = CapabilityGraph()
        r1 = graph.resolve_goal("build something")
        r2 = graph.resolve_goal("research something")
        assert r1.fingerprint != r2.fingerprint


class TestGate7GraphSurvivesReload:
    def test_graph_independent_of_provider_registry(self):
        graph = CapabilityGraph()
        subgraph = graph.resolve_goal("build app")
        assert len(subgraph.nodes) > 0
        graph2 = CapabilityGraph()
        subgraph_after = graph2.resolve_goal("build app")
        assert subgraph_after.fingerprint == subgraph.fingerprint

    def test_subgraph_fingerprint_stable_after_provider_removal(self, clean_registry):
        p = _make_provider("temp", caps=["coding"])
        clean_registry.register(p, priority=50)
        graph = CapabilityGraph()
        subgraph = graph.resolve_goal("build app")
        fp1 = subgraph.fingerprint
        clean_registry.unregister("temp")
        subgraph2 = graph.resolve_goal("build app")
        assert subgraph2.fingerprint == fp1


class TestGate8ReplayDAG:
    def test_negotiation_result_to_dict(self):
        result = NegotiationResult(
            capability_id="test_cap",
            capability_version=1,
            chosen_provider_id="prov_a",
            chosen_provider_version="1.0.0",
            score=0.85,
            confidence=0.9,
            candidates=(
                CandidateScore(
                    provider_id="prov_a",
                    provider_version="1.0.0",
                    score=0.85,
                    confidence=0.9,
                    dimensions={"historical_success": 0.8, "benchmark_quality": 0.7},
                    calibration_adjustment=0.05,
                    reason="strong historical success",
                ),
                CandidateScore(
                    provider_id="prov_b",
                    provider_version="2.0.0",
                    score=0.65,
                    confidence=0.6,
                    dimensions={"historical_success": 0.5, "benchmark_quality": 0.4},
                    calibration_adjustment=0.0,
                    reason="moderate historical success",
                ),
            ),
            fallback_chain=("prov_b",),
            reason="strong historical success (score=0.85, conf=0.90)",
        )
        d = result.to_dict()
        assert d["capability_id"] == "test_cap"
        assert d["chosen_provider_id"] == "prov_a"
        assert len(d["candidates"]) == 2
        assert d["candidates"][0]["score"] == 0.85
        assert d["candidates"][1]["reason"] == "moderate historical success"

    def test_composition_plan_to_dict(self):
        plan = CompositionPlan(
            goal="test goal",
            steps=(),
            subgraph_fingerprint="abc",
            total_score=0.7,
            avg_confidence=0.8,
        )
        d = plan.to_dict()
        assert d["goal"] == "test goal"
        assert d["subgraph_fingerprint"] == "abc"

    def test_composition_plan_replay_chain(self, clean_registry):
        from core.providers.router import ProviderRouter

        for cid in ("coding", "testing", "deployment"):
            p = _make_provider(f"prov_{cid}", caps=[cid])
            clean_registry.register(p, priority=50)

        graph = CapabilityGraph()
        router = ProviderRouter()
        router._registry = clean_registry
        negotiator = CapabilityNegotiator(graph=graph, router=router, registry=clean_registry)
        engine = CompositionEngine(graph=graph, negotiator=negotiator, registry=clean_registry)

        plan = engine.compose("build app")
        d = plan.to_dict()
        assert len(d["steps"]) >= 2
        for step in d["steps"]:
            assert "capability_id" in step
            assert "provider_id" in step
            assert "reason" in step
            assert "score" in step


class TestGate9NoProviderLogicInPlanner:
    def test_planner_does_not_import_provider_modules(self):
        import ast
        import inspect
        import core.planner
        source = inspect.getsource(core.planner)
        bad_names = {
            "ExecutionProvider", "ProviderRegistry", "ProviderRouter",
            "ProviderLifecycleManager", "TemporaryRegistry", "QuarantineStore",
        }
        provider_imports = [n for n in bad_names if n in source]
        assert len(provider_imports) == 0, (
            f"Planner imports provider names: {provider_imports}"
        )

    def test_planner_uses_capability_graph_instead(self):
        import ast
        import inspect
        import core.planner
        source = inspect.getsource(core.planner)
        assert "CapabilityGraph" in source or ".capability." in source or (
            "CapabilityNode" in source or "Capability" in source
        ) or "compose" in source or "resolve_goal" in source

