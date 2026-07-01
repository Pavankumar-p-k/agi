# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");

"""JARVIS version information."""

__version__ = "3.0.0-rc3"
VERSION = __version__
VERSION_INFO = (3, 0, 0, "rc3")
PROJECT = "JARVIS"
DESCRIPTION = "Autonomous AI workspace orchestrator"
PROVIDER_SDK_VERSION = "2"
CAPABILITY_GRAPH_VERSION = "2"


def version_string() -> str:
    import platform, sys
    return (
        f"JARVIS {VERSION}\n"
        f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}\n"
        f"Platform {platform.system()} {platform.release()}\n"
        f"Provider SDK v{PROVIDER_SDK_VERSION}\n"
        f"Capability Graph v{CAPABILITY_GRAPH_VERSION}"
    )
