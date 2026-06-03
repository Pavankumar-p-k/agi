from skills.utils import success_response, error_response

async def latex_math(params: dict) -> dict:
    """Execute the latex_math task."""
    # TODO: Implement full logic for latex_math
    return success_response({"result": f"Executed latex_math with params: {params}"} )

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        # Register the tool with JARVIS
        pass
