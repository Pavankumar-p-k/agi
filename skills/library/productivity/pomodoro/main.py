from skills.utils import success_response, error_response

async def pomodoro(params: dict) -> dict:
    """Execute the pomodoro task."""
    # TODO: Implement full logic for pomodoro
    return success_response({"result": f"Executed pomodoro with params: {params}"} )

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        # Register the tool with JARVIS
        pass
