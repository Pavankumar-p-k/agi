"""
Deprecated — use core.planner.dag instead.

This module re-exports TaskNode and TaskGraph from the canonical
core.planner.dag module for backward compatibility.

Deprecated: Phase 4
Remove after: Phase 8
"""
import warnings

from core.planner.dag import TaskGraph, TaskNode  # noqa: F401

warnings.warn(
    "brain.planner.task_graph is deprecated. Use 'core.planner.dag' instead.",
    DeprecationWarning, stacklevel=2,
)
