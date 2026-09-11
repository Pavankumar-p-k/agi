from core.desktop.adapters import AdapterRegistry, FileExplorerAdapter
from core.desktop.applications import ApplicationRegistry
from core.desktop.capabilities import CapabilityCatalog
from core.desktop.task_packs import TaskPack, TaskPackStep


def test_capability_catalog_integrates_apps_adapters_and_packs(tmp_path):
    apps = ApplicationRegistry(
        tmp_path / "apps.json",
        lambda: {"programs": [{"Name": "Explorer", "Version": "1"}]},
        lambda: [],
    )
    apps.refresh()
    catalog = CapabilityCatalog(apps, AdapterRegistry([FileExplorerAdapter()]), tmp_path / "profiles.json")
    pack = TaskPack("explorer-discovery", "Explorer", (TaskPackStep("discover", "discover"),))
    profile = catalog.refresh([pack])[0]
    assert profile.adapter == "explorer"
    assert profile.safe_task_packs == ["explorer-discovery"]
    assert "open" in profile.supported_actions


def test_capability_catalog_refuses_unknown_adapter_actions(tmp_path):
    apps = ApplicationRegistry(
        tmp_path / "apps.json",
        lambda: {"programs": [{"Name": "Unknown"}]},
        lambda: [],
    )
    apps.refresh()
    catalog = CapabilityCatalog(apps, AdapterRegistry(), tmp_path / "profiles.json")
    profile = catalog.refresh()[0]
    assert profile.adapter is None
    assert profile.supported_actions == []
