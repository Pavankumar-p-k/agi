from skills.utils import success_response, error_response

async def bill_reminder(params: dict) -> dict:
    """Execute the bill_reminder task."""
    # TODO: Implement full logic for bill_reminder
    return success_response({"result": f"Executed bill_reminder with params: {params}"} )

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        # Register the tool with JARVIS
        pass
