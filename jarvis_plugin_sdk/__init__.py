
from typing import Any, Callable, TypeVar, Union

T = TypeVar("T", bound=Callable[..., Any])

def hook(name: str):
    """
    Decorator to mark a method as a JARVIS hook handler.
    Example:
        @hook("on_agent_reply")
        def my_handler(self, reply: str):
            ...
    """
    def decorator(func: T) -> T:
        func._jarvis_hook = name
        return func
    return decorator

class Plugin:
    """
    Base class for JARVIS plugins.
    """
    name: str = ""
    description: str = ""
    version: str = "0.1.0"
    author: str = ""

    def __init__(self):
        pass

    def on_load(self):
        """Called when the plugin is loaded."""
        pass

    def on_unload(self):
        """Called when the plugin is unloaded."""
        pass
