"""MJ Core — a headless, software-only assistant kernel.

This package is the "one brain, one source of truth" foundation: a SQLite
state store, an append-only event log, a hash-chained audit log, a capability
registry, and a policy gate. No LLM calls happen in this package (``core``).
"""

__version__ = "0.1.0"

# Invariant 10 of the plan: awareness before autonomy. The system starts at
# L0 (observe-only) and may never raise this constant without evidence.
AUTONOMY_LEVEL = "L0"
