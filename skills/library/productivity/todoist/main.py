from skills.utils import success_response, error_response

async def todoist(params: dict) -> dict:
    """Execute the todoist task."""
    # TODO: Implement full logic for todoist
    return success_response({"result": f"Executed todoist with params: {params}"} )

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        # Register the tool with JARVIS
        pass
