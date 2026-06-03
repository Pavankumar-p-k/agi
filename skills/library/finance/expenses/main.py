from skills.utils import success_response, error_response

async def expenses(params: dict) -> dict:
    """Execute the expenses task."""
    # TODO: Implement full logic for expenses
    return success_response({"result": f"Executed expenses with params: {params}"} )

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        # Register the tool with JARVIS
        pass
