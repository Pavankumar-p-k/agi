from core.desktop.applications import ApplicationRegistry


def test_application_registry_refreshes_and_filters(tmp_path):
    registry = ApplicationRegistry(
        tmp_path / "apps.json",
        lambda: {"programs": [{"Name": "Editor", "Version": "1.0", "InstallLocation": "C:\\Editor"}]},
        lambda: [{"title": "Editor - project.txt"}],
    )
    records = registry.refresh()
    assert records[0].windows == ["Editor - project.txt"]
    assert registry.list("edit")[0].version == "1.0"


def test_application_approval_persists(tmp_path):
    path = tmp_path / "apps.json"
    registry = ApplicationRegistry(path, lambda: {"programs": [{"Name": "Editor"}]}, lambda: [])
    registry.refresh()
    assert registry.approve("Editor").approved is True
    reloaded = ApplicationRegistry(path, lambda: {"programs": []}, lambda: [])
    assert reloaded.list("editor")[0].approved is True
