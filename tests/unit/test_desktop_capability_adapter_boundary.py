from core.desktop.adapters import AdapterRegistry, FileExplorerAdapter
from core.desktop.applications import ApplicationRegistry
from core.desktop.capabilities import CapabilityCatalog


def test_registered_shell_adapter_has_capability_without_uninstall_entry(tmp_path):
    apps = ApplicationRegistry(
        tmp_path / "apps.json",
        lambda: {"programs": []},
        lambda: [],
    )
    catalog = CapabilityCatalog(
        apps,
        AdapterRegistry([FileExplorerAdapter()]),
        tmp_path / "profiles.json",
    )
    profiles = catalog.refresh()
    assert profiles[0].application == "explorer"
    assert profiles[0].supported_actions == ["open", "reveal"]
