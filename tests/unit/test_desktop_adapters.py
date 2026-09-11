import pytest

from core.desktop.adapters import AdapterRegistry, FileExplorerAdapter, TextEditorAdapter, ProcessInspectionAdapter, ClipboardAdapter, WindowManagementAdapter


def test_file_explorer_adapter_delegates_to_shared_actions():
    adapter = FileExplorerAdapter()
    actions = type("Actions", (), {
        "reveal_in_explorer": lambda self, path: {"success": True, "path": path},
        "open_with": lambda self, path, app: {"success": True, "path": path, "app": app},
    })()
    assert adapter.reveal("C:\\temp", actions)["success"] is True
    assert adapter.open("C:\\temp\\a.txt", actions, "notepad")["app"] == "notepad"


def test_adapter_registry_is_centralized():
    registry = AdapterRegistry([FileExplorerAdapter()])
    assert registry.supports("Explorer", "reveal") is True
    assert registry.supports("Explorer", "delete") is False
    assert registry.get("missing") is None
    with pytest.raises(ValueError):
        registry.register(type("Bad", (), {"application": " ", "supports": lambda self, action: False})())


def test_text_editor_adapter_delegates_file_actions():
    adapter = TextEditorAdapter()
    actions = type("Actions", (), {
        "open_with": lambda self, path, app: {"success": True, "app": app},
        "read_file": lambda self, path: {"success": True, "path": path},
        "write_file": lambda self, path, content: {"success": True, "bytes": len(content)},
    })()
    assert adapter.open("a.txt", actions)["app"] == "notepad"
    assert adapter.read("a.txt", actions)["success"] is True
    assert adapter.write("a.txt", "hello", actions)["bytes"] == 5


def test_process_inspection_adapter_is_read_only():
    class Monitor:
        def list_processes(self, limit):
            return [type("Snapshot", (), {"name": "notepad.exe", "pid": 1})()]
        def find_by_name(self, name):
            return []
        def is_running(self, name):
            return False

    adapter = ProcessInspectionAdapter()
    assert adapter.supports("list") is True
    assert adapter.list(Monitor())["processes"][0]["name"] == "notepad.exe"
    assert adapter.is_running("notepad", Monitor())["running"] is False


def test_clipboard_adapter_delegates_manager():
    class Result:
        success = True
        content = "hello"
        error = ""
    class Clipboard:
        def get_text(self):
            return "hello"
        def set_text(self, text):
            return Result()
        def clear(self):
            return Result()

    adapter = ClipboardAdapter()
    assert adapter.read(Clipboard())["content"] == "hello"
    assert adapter.write("hello", Clipboard())["success"] is True


def test_window_adapter_exposes_only_non_destructive_actions():
    class Controller:
        def list_windows(self):
            return [{"title": "Editor"}]
        def focus(self, title):
            return type("Result", (), {"success": True, "error": "", "details": {}})()
        def minimize(self, title):
            return type("Result", (), {"success": True, "error": "", "details": {}})()
        def maximize(self, title):
            return type("Result", (), {"success": True, "error": "", "details": {}})()

    adapter = WindowManagementAdapter()
    assert adapter.list(Controller())["count"] == 1
    assert adapter.focus("Editor", Controller())["success"] is True
    assert adapter.supports("close") is False
