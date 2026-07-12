"""
Deprecated — use core.planner instead.
"""

import warnings

from .task_graph import TaskGraph, TaskNode
from .planner import Planner

__all__ = [
    "TaskGraph",
    "TaskNode",
    "Planner",
]

warnings.warn(
    "brain.planner is deprecated. Use 'core.planner.dag' for TaskGraph/TaskNode "
    "and 'core.planner.protocol' for the Planner interface.",
    DeprecationWarning, stacklevel=2,
)
