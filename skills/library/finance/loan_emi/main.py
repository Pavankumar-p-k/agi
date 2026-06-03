from skills.utils import success_response, error_response

async def loan_emi(params: dict) -> dict:
    """Execute the loan_emi task."""
    # TODO: Implement full logic for loan_emi
    return success_response({"result": f"Executed loan_emi with params: {params}"} )

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        # Register the tool with JARVIS
        pass
