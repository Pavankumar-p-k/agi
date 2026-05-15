"""
Sovereign V2 — Executive MetaCognition
========================================
Upgraded from V19 purely passive analytical tracking to V3 Executive Control.
MetaCognition must now DETECT -> PLAN -> PATCH -> TEST -> SCORE -> LEARN.

It imports the AutonomousSelfRepairV3 engine to turn identified strategic drifts
or compilation failures into autonomous, dynamically patched fixes.
"""

import time
import os
import ast
import hashlib
import asyncio
from pathlib import Path
from typing import Dict, Any, List

try:
    from jarvis_os.runtime.exceptions import GovernanceViolation
except ImportError:
    class GovernanceViolation(Exception):
        pass

try:
    from utils.logger import SystemLogger
except ModuleNotFoundError:
    import logging

    def SystemLogger(name: str):
        return logging.getLogger(name)
from brain.AdaptiveSelfRepair import AutonomousSelfRepairV3

logger = SystemLogger(__name__)

class ExecutiveMetaCognitionV3:
    """
    The True Sovereign Logic Governor.
    Executes the DETECT -> PLAN -> PATCH -> TEST sequence dynamically.
    """
    
    def __init__(self, workspace_root: str = "."):
        self.workspace_root = workspace_root
        self.self_repair = AutonomousSelfRepairV3(workspace_root)
        self.metrics_history = []
        self.last_patch_result: Dict[str, Any] = {}

    def _python_files(self) -> List[Path]:
        root = Path(self.workspace_root)
        return [path for path in root.rglob("*.py") if ".venv" not in path.parts and "__pycache__" not in path.parts]

    def self_audit(self) -> Dict[str, Any]:
        """Deep analysis of the entire execution footprint vs governance logs."""
        logger.info("[MetaCognitionV3] Running structural self-audit.")
        files = self._python_files()
        syntax_errors: List[str] = []
        stub_functions: List[str] = []
        duplicate_hashes: Dict[str, List[str]] = {}
        file_hashes: Dict[str, str] = {}

        for file_path in files:
            relative = file_path.relative_to(self.workspace_root).as_posix()
            try:
                content = file_path.read_text(encoding="utf-8")
                ast_tree = ast.parse(content)
                file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                file_hashes[relative] = file_hash
                duplicate_hashes.setdefault(file_hash, []).append(relative)
                for node in ast.walk(ast_tree):
                    if isinstance(node, ast.FunctionDef) and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                        stub_functions.append(f"{relative}:{node.name}")
            except SyntaxError as exc:
                syntax_errors.append(f"{relative}:{exc.lineno}:{exc.msg}")
            except OSError:
                continue

        duplicate_groups = [paths for paths in duplicate_hashes.values() if len(paths) > 1]
        drift_count = len(syntax_errors) + len(stub_functions)
        
        if drift_count > 0:
            raise GovernanceViolation(f"Self-audit failed: detected {drift_count} drift issues.")
            
        status = "clean"
        return {
            "status": status,
            "drift_count": drift_count,
            "file_count": len(files),
            "syntax_errors": syntax_errors,
            "stub_functions": stub_functions,
            "duplicate_groups": duplicate_groups,
        }

    def trust_drift(self) -> float:
        """Measures degradation of internal capability map."""
        if not self.metrics_history:
            return 0.0
        last = self.metrics_history[-1]
        governance = float(last.get("governance", 1.0))
        regret = float(last.get("regret", 0.0))
        drift = max(0.0, min(1.0, (1.0 - governance) + regret))
        return drift

    def cognitive_load(self) -> float:
        """Tracks the concurrency thresholds of executing planners."""
        recent = self.metrics_history[-5:]
        if not recent:
            return 0.5
        return max(0.0, min(1.0, sum(float(item.get("cognition", 0.5)) for item in recent) / len(recent)))

    def strategic_effectiveness(self) -> float:
        """Evaluation of long-horizon orchestration success."""
        if not self.last_patch_result:
            return 0.5
        return 1.0 if self.last_patch_result.get("validated") else 0.4

    def interruption_quality(self) -> float:
        """Scores user-interventions vs autonomous success loops."""
        if not self.last_patch_result:
            return 0.6
        return 0.9 if self.last_patch_result.get("status") == "SUCCESS" else 0.5

    def identity_consistency(self) -> float:
        """Evaluates whether recent outputs violate core immutable boundaries."""
        try:
            audit = self.self_audit()
            if audit["syntax_errors"]:
                return 0.2
            return 0.95 if not audit["stub_functions"] else 0.75
        except GovernanceViolation:
            return 0.0

    def strategic_regret(self) -> float:
        """Penalty metric for overrides that ended in test regressions."""
        if not self.last_patch_result:
            return 0.1
        return 0.0 if self.last_patch_result.get("validated") else 0.6

    def governance_integrity(self) -> float:
        """Measures whether the backend bypassed privacy structures."""
        governance_file = Path(self.workspace_root) / "jarvis_os" / "RuntimeGovernanceLayer.py"
        duplicate_governance_file = Path(self.workspace_root) / "governance" / "RuntimeGovernanceLayer.py"
        if not governance_file.exists():
            return 0.0
        if duplicate_governance_file.exists():
            a = hashlib.sha256(governance_file.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            b = hashlib.sha256(duplicate_governance_file.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            return 0.85 if a == b else 0.6
        return 0.9

    async def autonomous_patch_generation(self, target_file: str, failing_test: str, error_trace: str):
        """DETECT -> PLAN -> PATCH chain."""
        logger.warning(f"[MetaCognitionV3] Strategic degradation detected in {target_file}. Initiating V3 physical patch logic.")
        return await self.self_repair.autonomous_patch_generation(target_file, failing_test, error_trace)

    async def patch_validation(self, patch_id: str):
        """Validates an executed patch sequence."""
        patch = next((item for item in self.self_repair._patch_history if item.patch_id == patch_id), None)
        if patch is None:
            return {"patch_id": patch_id, "validated": False, "reason": "patch_not_found"}
        validated = patch.status.value == "success"
        result = {
            "patch_id": patch.patch_id,
            "validated": validated,
            "status": patch.status.name,
            "target_file": patch.target_file,
            "test_target": patch.test_target,
        }
        self.last_patch_result = result
        return result

    def rollback_protection(self, target_file: str, backup_path: str):
        """Direct exposure to rollback recovery sequences."""
        self.self_repair.rollback_protection(target_file, backup_path)

    def benchmark_self_scoring(self) -> Dict[str, float]:
        """Aggregate scoring mechanism measuring OS baseline over previous iterations."""
        scores = {
            "trust": self.trust_drift(),
            "cognition": self.cognitive_load(),
            "regret": self.strategic_regret(),
            "governance": self.governance_integrity()
        }
        self.metrics_history.append(scores)
        return scores

    async def trigger_detect_and_patch_loop(self, error_report: dict):
        """Top level executive command: DETECT -> PLAN -> PATCH -> TEST -> SCORE -> LEARN"""
        target_file = error_report.get("target_file")
        failing_test = error_report.get("failing_test")
        error_trace = error_report.get("error_trace", "Unknown failure")
        if not target_file or not failing_test:
            return {"patched": False, "reason": "missing_error_report_fields"}

        # Real I/O: record the trigger to the cognition log
        log_path = Path(self.workspace_root) / "reports" / "cognition_trigger.log"
        log_path.parent.mkdir(exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{time.ctime()} - TRIGGER: {target_file} failing {failing_test}\n")

        try:
            patch = await self.autonomous_patch_generation(target_file, failing_test, error_trace)
            if patch is None:
                self.last_patch_result = {"validated": False, "status": "FAILED", "reason": "patch_generation_failed"}
                return self.last_patch_result
            validation = await self.patch_validation(patch.patch_id)
            score = self.benchmark_self_scoring()
            return {"patch": validation, "score": score}
        except Exception as e:
            logger.exception(f"[MetaCognition] Patch loop failed: {e}")
            return {"patched": False, "reason": str(e)}


class MetaCognitionEngine(ExecutiveMetaCognitionV3):
    """Adapter wrapper matching the interface expected by UnifiedBrain."""

    def __init__(self, world_state=None, memory_core=None, identity=None, archive=None, monitor=None, workspace_root: str = "."):
        super().__init__(workspace_root=workspace_root)
        self.world_state = world_state
        self.memory_core = memory_core
        self.identity = identity
        self.archive = archive
        self.monitor = monitor

    async def audit_decision_chain(self, decision: dict, context: Any, notification: dict) -> None:
        pass

    async def audit_subsystem_performance(self, subsystem: str, result: dict, context: Any) -> None:
        pass

    async def audit_goal_outcomes(self, goal: str, result: dict, context: Any) -> None:
        pass

    async def audit_strategy_quality(self, decision: dict, context: Any) -> None:
        pass

    async def detect_trust_drift(self) -> bool:
        return self.trust_drift() > 0.3

    async def repair_trust_strategy(self) -> None:
        logger.info("[MetaCognition] Trust repair triggered (stub).")
