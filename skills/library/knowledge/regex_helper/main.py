from skills.utils import success_response, error_response

async def regex_helper(params: dict) -> dict:
    """Execute the regex_helper task."""
    # TODO: Implement full logic for regex_helper
    return success_response({"result": f"Executed regex_helper with params: {params}"} )

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        # Register the tool with JARVIS
        pass
