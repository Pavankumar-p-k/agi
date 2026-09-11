class InterruptManager:
    def __init__(self):
        self._paused: set[str] = set()

    def signal_pause(self, project_name: str) -> None:
        self._paused.add(project_name)

    def check_and_handle(self, state) -> bool:
        if state.project_name in self._paused:
            state.status = "paused"
            state.save()
            return True
        return False


interrupt_manager = InterruptManager()
