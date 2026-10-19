"""World model: probes that produce facts with provenance, TTL and labels.

Questions about the machine (plan phases 2 and 12.1) are answered from here.
Every fact carries where it came from, when it was observed, how long it is
good for, and a label: verified (observed directly), reported, or stale
(older than its TTL).
"""
