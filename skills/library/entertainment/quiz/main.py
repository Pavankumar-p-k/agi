from skills.utils import success_response, error_response

async def quiz(params: dict) -> dict:
    """Execute the quiz task."""
    # TODO: Implement full logic for quiz
    return success_response({"result": f"Executed quiz with params: {params}"} )

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        # Register the tool with JARVIS
        pass
