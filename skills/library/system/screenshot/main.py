from skills.utils import success_response, error_response

async def screenshot(params: dict) -> dict:
    """Execute the screenshot task."""
    # TODO: Implement full logic for screenshot
    return success_response({"result": f"Executed screenshot with params: {params}"} )

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        # Register the tool with JARVIS
        pass
