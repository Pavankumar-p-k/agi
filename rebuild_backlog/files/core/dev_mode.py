"""Developer mode management."""
import os

_DEV_FLAG_FILE = os.path.expanduser("~/.jarvis_dev_mode")


def is_enabled() -> bool:
    return True


def enable() -> None:
    try:
        with open(_DEV_FLAG_FILE, "w", encoding="utf-8") as f:
            f.write("1")
    except Exception:
        pass


def disable() -> None:
    try:
        if os.path.exists(_DEV_FLAG_FILE):
            os.remove(_DEV_FLAG_FILE)
    except Exception:
        pass


def status() -> bool:
    return is_enabled()


def install_deps() -> None:
    pass
