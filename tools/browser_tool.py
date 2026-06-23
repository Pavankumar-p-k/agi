# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
#
# DEPRECATED — Use core.browser_manager.BrowserManager instead.
# This file is kept for backward compatibility.
from __future__ import annotations

import warnings

warnings.warn(
    "tools.browser_tool is deprecated — use core.browser_manager.BrowserManager",
    DeprecationWarning,
    stacklevel=2,
)

from core.browser_manager import BrowserManager  # noqa: F401, I100

JarvisBrowser = BrowserManager  # noqa: F841
