from skills.utils import success_response, error_response

async def budget(params: dict) -> dict:
    """Execute the budget task."""
    # TODO: Implement full logic for budget
    return success_response({"result": f"Executed budget with params: {params}"} )

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        # Register the tool with JARVIS
        pass
