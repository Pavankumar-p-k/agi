from skills.utils import success_response, error_response

async def recipe(params: dict) -> dict:
    """Execute the recipe task."""
    # TODO: Implement full logic for recipe
    return success_response({"result": f"Executed recipe with params: {params}"} )

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        # Register the tool with JARVIS
        pass
