from skills.utils import success_response, error_response

async def dictionary(params: dict) -> dict:
    """Execute the dictionary task."""
    # TODO: Implement full logic for dictionary
    return success_response({"result": f"Executed dictionary with params: {params}"} )

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        # Register the tool with JARVIS
        pass
