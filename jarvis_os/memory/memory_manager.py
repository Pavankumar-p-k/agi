class MemoryManager:
    def __init__(self, config=None):
        self._store = {}
        self.config = config

    def get(self, key: str, default=None):
        return self._store.get(key, default)

    def put(self, key: str, value) -> None:
        self._store[key] = value

    def clear(self) -> None:
        self._store.clear()
