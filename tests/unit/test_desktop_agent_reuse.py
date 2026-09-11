import jarvis_desktop_agent as agent


class _ProcessMonitor:
    def __init__(self, running=False):
        self.running = running

    def is_running(self, _name):
        return self.running


class _LaunchResult:
    success = True
    error = ""


def test_launch_app_focuses_existing_common_app(monkeypatch):
    monkeypatch.setattr(agent, "ProcessMonitor", lambda: _ProcessMonitor(True))
    monkeypatch.setattr(agent.U, "_app_pids", lambda _name: [1234])
    monkeypatch.setattr(agent.wc, "list_windows", lambda: [{"title": "Calculator"}])
    monkeypatch.setattr(agent.U, "focus_window_win32", lambda title: {"success": True, "window": title})
    launch = lambda _name: (_ for _ in ()).throw(AssertionError("must not launch"))
    monkeypatch.setattr(agent.dc, "launch_app", launch)

    result = agent.launch_app("calc")

    assert result["success"] is True
    assert result["action"] == "focused_existing"
    assert result["window"] == "Calculator"


def test_launch_app_launches_only_when_no_existing_instance(monkeypatch):
    monkeypatch.setattr(agent, "ProcessMonitor", lambda: _ProcessMonitor(False))
    monkeypatch.setattr(agent.U, "_app_pids", lambda _name: [])
    monkeypatch.setattr(agent.wc, "list_windows", lambda: [])
    monkeypatch.setattr(agent.dc, "launch_app", lambda _name: _LaunchResult())

    result = agent.launch_app("notepad")

    assert result == {
        "success": True,
        "action": "launched",
        "app": "notepad",
        "error": "",
    }


def test_launch_app_reuses_explorer_window_by_alias(monkeypatch):
    monkeypatch.setattr(agent, "ProcessMonitor", lambda: _ProcessMonitor(True))
    monkeypatch.setattr(agent.U, "_app_pids", lambda _name: [2222])
    monkeypatch.setattr(agent.wc, "list_windows", lambda: [{"title": "Desktop - File Explorer"}])
    monkeypatch.setattr(agent.U, "focus_window_win32", lambda title: {"success": True, "window": title})

    result = agent.launch_app("explorer.exe")

    assert result["action"] == "focused_existing"
    assert result["window"] == "Desktop - File Explorer"


def test_browse_to_opens_new_tab_without_replacing_active_tab(monkeypatch):
    calls = []
    monkeypatch.setattr(agent.U, "focus_tab", lambda *_args: {"success": False})
    monkeypatch.setattr(agent.U, "_app_pids", lambda _name: [3333])
    monkeypatch.setattr(agent.U, "focus_window_win32", lambda title: {"success": True, "window": title})
    monkeypatch.setattr(agent.dc, "hotkey", lambda *keys: calls.append(("hotkey", keys)))
    monkeypatch.setattr(agent.dc, "type_text", lambda text, interval: calls.append(("type", text)))
    monkeypatch.setattr(agent.dc, "press_key", lambda key: calls.append(("press", key)))
    monkeypatch.setattr(agent.time, "sleep", lambda _seconds: None)
    agent.TASK_BROWSER_TABS_OPENED = 0

    result = agent.browse_to("https://example.com", new_tab=True)

    assert result["opened_new_tab"] is True
    assert ("hotkey", ("ctrl", "t")) in calls
    assert ("hotkey", ("ctrl", "l")) not in calls

def test_browse_to_rejects_unverified_new_tab(monkeypatch):
    monkeypatch.setattr(agent.U, "focus_tab", lambda *_args: {"success": False})
    monkeypatch.setattr(agent.U, "_app_pids", lambda _name: [3333])
    monkeypatch.setattr(agent.U, "focus_window_win32", lambda _title: {
        "success": True, "window": "Chrome"
    })
    monkeypatch.setattr(agent.dc, "hotkey", lambda *_keys: None)
    monkeypatch.setattr(agent.dc, "type_text", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(agent.dc, "press_key", lambda *_args: None)
    monkeypatch.setattr(agent.time, "sleep", lambda _seconds: None)
    agent.TASK_BROWSER_TABS_OPENED = 0

    result = agent.browse_to("https://www.youtube.com/watch?v=controlled", new_tab=True)

    assert result["success"] is False
    assert result["opened_new_tab"] is True
    assert "verify" in result["error"].lower()



def test_browse_to_reuses_matching_tab(monkeypatch):
    monkeypatch.setattr(agent.U, "focus_tab", lambda _app, _title: {
        "success": True,
        "window": "Chrome",
    })
    agent.TASK_BROWSER_TABS_OPENED = 0

    result = agent.browse_to("https://example.com/form", new_tab=True)

    assert result["reused"] is True
    assert result.get("opened_new_tab", False) is False


def test_launch_app_matches_arbitrary_installed_app_by_process_and_title(monkeypatch):
    monkeypatch.setattr(agent, "ProcessMonitor", lambda: _ProcessMonitor(True))
    monkeypatch.setattr(agent.U, "_app_pids", lambda _name: [])
    monkeypatch.setattr(agent.U, "list_running_apps", lambda: {
        "apps": [{"Name": "Code.exe", "Title": "project - Visual Studio Code"}]
    })
    monkeypatch.setattr(agent.wc, "list_windows", lambda: [
        {"title": "project - Visual Studio Code"}
    ])
    monkeypatch.setattr(agent.U, "focus_window_win32", lambda title: {
        "success": True, "window": title
    })
    monkeypatch.setattr(agent.dc, "launch_app", lambda _name: (
        _ for _ in ()
    ).throw(AssertionError("must reuse installed app")))

    result = agent.launch_app("Visual Studio Code")

    assert result["action"] == "focused_existing"
    assert result["window"] == "project - Visual Studio Code"


def test_launch_app_falls_back_to_windows_search_for_installed_app(monkeypatch):
    monkeypatch.setattr(agent, "ProcessMonitor", lambda: _ProcessMonitor(False))
    monkeypatch.setattr(agent.U, "_app_pids", lambda _name: [])
    monkeypatch.setattr(agent.U, "list_running_apps", lambda: {"apps": []})
    monkeypatch.setattr(agent.wc, "list_windows", lambda: [])
    monkeypatch.setattr(agent.dc, "launch_app", lambda _name: _LaunchResultWithError())
    monkeypatch.setattr(agent, "_start_menu_launch", lambda name: {
        "success": True, "method": "start_menu_search", "app": name
    })

    result = agent.launch_app("Blender")

    assert result["success"] is True
    assert result["method"] == "start_menu_search"


def test_paint_window_matching_rejects_unrelated_search_title():
    assert agent._app_matches_window("paint", "rypaint - Search - Personal - Microsoft Edge") is False
    assert agent._app_matches_window("paint", "Untitled - Paint") is True


def test_launch_paint_uses_mspaint_executable(monkeypatch):
    launched = []
    monkeypatch.setattr(agent, "ProcessMonitor", lambda: _ProcessMonitor(False))
    monkeypatch.setattr(agent.U, "_app_pids", lambda _name: [])
    monkeypatch.setattr(agent.U, "list_running_apps", lambda: {"apps": []})
    monkeypatch.setattr(agent.wc, "list_windows", lambda: [])
    monkeypatch.setattr(agent, "_resolve_app", lambda _name: r"C:\Windows\System32\mspaint.exe")
    monkeypatch.setattr(agent.dc, "launch_app", lambda name: (
        launched.append(name) or _LaunchResult()
    ))

    result = agent.launch_app("paint")

    assert result["success"] is True
    assert launched == [r"C:\Windows\System32\mspaint.exe"]


class _LaunchResultWithError:
    success = False
    error = "not on PATH"
