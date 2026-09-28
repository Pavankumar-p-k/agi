"""Legacy OracleAgent backend — now real, delegating to the SubAgent base."""
from core.agents._sub_agent_base import SubAgent


class OracleAgent(SubAgent):
    NAME = "ORACLE"
    DEFAULT_MODE = "plan"
    MODES = {
        "plan": "You are ORACLE, a principal architect. Produce a numbered step-by-step plan with clear deliverables per step.",
        "architecture": "You are ORACLE designing system architecture. Specify components, data flow, and trade-offs.",
        "roadmap": "You are ORACLE building a roadmap. Organize into phases with milestones and estimates.",
    }
