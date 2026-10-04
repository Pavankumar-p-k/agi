"""Interactive setup engine."""
class SetupEngine:
    def resume_needed(self) -> bool:
        return False

    def run_full_setup(self, on_message=None, on_confirm=None, on_choice=None) -> bool:
        return True
