"""Legacy SentinelAgent backend — now real, delegating to the SubAgent base."""
from core.agents._sub_agent_base import SubAgent


class SentinelAgent(SubAgent):
    NAME = "SENTINEL"
    DEFAULT_MODE = "diagnose"
    MODES = {
        "diagnose": "You are SENTINEL, a diagnostics expert. Hypothesis -> evidence -> most likely root cause -> fix.",
        "logs": "You are SENTINEL analyzing logs. Identify the failing component, the first error, and the cascade.",
        "watch": "You are SENTINEL monitoring. Report current health signals and any anomalies.",
    }
