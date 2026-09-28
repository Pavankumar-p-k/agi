"""Legacy CipherAgent backend — now real, delegating to the SubAgent base."""
from core.agents._sub_agent_base import SubAgent


class CipherAgent(SubAgent):
    NAME = "CIPHER"
    DEFAULT_MODE = "audit"
    MODES = {
        "audit": "You are CIPHER, a security auditor. List findings ordered by severity (CRITICAL/HIGH/MEDIUM/LOW) with fixes.",
        "threats": "You are CIPHER threat-modeling. Use STRIDE to enumerate threats and mitigations.",
        "harden": "You are CIPHER hardening a system. Give concrete, prioritized hardening steps.",
    }
