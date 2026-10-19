"""Kernel: task store, event log, audit chain, capability registry, policy gate.

Kernel modules contain no LLM calls and never import from ``brain``. The
dependency arrow points one way: brain/executor/gateway may import core,
never the reverse.
"""
