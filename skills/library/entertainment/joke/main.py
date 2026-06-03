from skills.utils import success_response, error_response

async def joke(params: dict) -> dict:
    """Execute the joke task."""
    # TODO: Implement full logic for joke
    return success_response({"result": f"Executed joke with params: {params}"} )

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        # Register the tool with JARVIS
        pass
