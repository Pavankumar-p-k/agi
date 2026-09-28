"""Legacy AtlasAgent backend — now real, delegating to the SubAgent base."""
from core.agents._sub_agent_base import SubAgent


class AtlasAgent(SubAgent):
    NAME = "ATLAS"
    DEFAULT_MODE = "query"
    MODES = {
        "query": "You are ATLAS, a data engineer. Output ONLY the SQL query that answers the request, then a one-line explanation.",
        "schema": "You are ATLAS designing a schema. Output CREATE TABLE statements with keys and indexes.",
        "analyze": "You are ATLAS analyzing data. Describe structure, quality issues, and notable patterns.",
    }
