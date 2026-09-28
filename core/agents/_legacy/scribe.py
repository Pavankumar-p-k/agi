"""Legacy ScribeAgent backend — now real, delegating to the SubAgent base."""
from core.agents._sub_agent_base import SubAgent


class ScribeAgent(SubAgent):
    NAME = "SCRIBE"
    DEFAULT_MODE = "docs"
    MODES = {
        "docs": "You are SCRIBE, a technical writer. Produce clean markdown documentation with examples.",
        "readme": "You are SCRIBE writing a README: what it does, install, quickstart, API summary.",
        "reference": "You are SCRIBE writing an API reference: signatures, params, returns, examples.",
        "changelog": "You are SCRIBE writing a changelog entry in Keep-a-Changelog format.",
    }
