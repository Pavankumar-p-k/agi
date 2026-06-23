# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""High-fidelity visual components for the JARVIS CLI redesign."""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.layout import Layout
from rich.style import Style
from rich.align import Align

console = Console()

class JARVISTheme:
    """Production themes for JARVIS CLI."""
    CYBERPUNK = {
        "accent": "magenta",
        "primary": "cyan",
        "secondary": "blue",
        "success": "spring_green1",
        "error": "bright_red",
        "warning": "bright_yellow",
        "border": "magenta",
        "bg": "grey7",
    }
    NOIR = {
        "accent": "white",
        "primary": "grey70",
        "secondary": "grey50",
        "success": "grey93",
        "error": "grey30",
        "warning": "grey82",
        "border": "grey30",
        "bg": "black",
    }
    EMERALD = {
        "accent": "green",
        "primary": "spring_green2",
        "secondary": "dark_green",
        "success": "green",
        "error": "red",
        "warning": "yellow",
        "border": "green",
        "bg": "grey3",
    }
    OCEAN = {
        "accent": "blue",
        "primary": "light_sky_blue1",
        "secondary": "deep_sky_blue3",
        "success": "aquamarine1",
        "error": "indian_red1",
        "warning": "wheat1",
        "border": "blue",
        "bg": "grey3",
    }

    _current = CYBERPUNK

    @classmethod
    def set(cls, theme_name: str):
        mapping = {
            "cyberpunk": cls.CYBERPUNK,
            "noir": cls.NOIR,
            "emerald": cls.EMERALD,
            "ocean": cls.OCEAN
        }
        cls._current = mapping.get(theme_name.lower(), cls.CYBERPUNK)

    @classmethod
    def get(cls) -> dict:
        return cls._current

def get_pt_style():
    """Map Rich theme colors to prompt_toolkit styles with stable ANSI fallbacks."""
    theme = JARVISTheme.get()
    from prompt_toolkit.styles import Style as PtStyle
    
    # Mapping table for Rich-to-ANSI (for prompt_toolkit stability)
    ANSI_MAP = {
        "magenta": "ansimagenta",
        "cyan": "ansicyan",
        "blue": "ansiblue",
        "green": "ansigreen",
        "red": "ansired",
        "yellow": "ansiyellow",
        "white": "ansiwhite",
        "grey70": "ansigray",
        "grey50": "ansigray",
        "grey30": "ansigray",
        "grey93": "ansiwhite",
        "spring_green1": "ansigreen",
        "spring_green2": "ansigreen",
        "dark_green": "ansigreen",
        "light_sky_blue1": "ansicyan",
        "deep_sky_blue3": "ansiblue",
        "aquamarine1": "ansigreen",
        "indian_red1": "ansired",
        "wheat1": "ansiyellow",
        "bright_red": "ansired",
        "bright_yellow": "ansiyellow",
    }

    accent = ANSI_MAP.get(theme['accent'], "ansimagenta")
    secondary = ANSI_MAP.get(theme['secondary'], "ansiblue")
    
    return PtStyle.from_dict({
        "prompt": f"bold {accent}",
        "continuation": secondary,
    })

def get_accent(): return JARVISTheme.get()["accent"]
def get_primary(): return JARVISTheme.get()["primary"]
def get_border(): return JARVISTheme.get()["border"]

def render_banner():
    """Render a high-fidelity banner with system info."""
    theme = JARVISTheme.get()
    
    ascii_art = """
      ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
      ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
      ██║███████║██████╔╝██║   ██║██║███████╗
 ██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
 ╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
  ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝ v2.0
    """
    
    banner_text = Text(ascii_art, style=theme["accent"])
    info_table = Table.grid(padding=(0, 2))
    info_table.add_row(
        Text("OS: ", style=theme["secondary"]) + Text("JARVIS-CORE", style=theme["primary"]),
        Text("STATUS: ", style=theme["secondary"]) + Text("ONLINE", style=theme["success"]),
        Text("TIME: ", style=theme["secondary"]) + Text(datetime.now().strftime("%H:%M:%S"), style=theme["primary"]),
    )
    
    from rich.console import Group
    
    panel = Panel(
        Align.center(
            Group(
                Align.center(banner_text),
                Text("\n"),
                Align.center(info_table)
            )
        ),
        border_style=theme["border"],
        subtitle="[bold]Integrated Intelligence System[/]",
        subtitle_align="right"
    )
    console.print(panel)

def render_agent_status(agents_data: list):
    """Render a sleek grid of agent statuses."""
    theme = JARVISTheme.get()
    table = Table(title="Neural Network Agents", title_style=theme["accent"], border_style=theme["border"], expand=True)
    
    table.add_column("Agent", style=theme["accent"], no_wrap=True)
    table.add_column("Designation", style=theme["primary"])
    table.add_column("Status", justify="right")
    
    for agent in agents_data:
        status_text = Text("● READY", style=theme["success"]) if agent["ready"] else Text("○ OFFLINE", style="dim")
        table.add_row(agent["name"], agent["role"], status_text)
    
    console.print(table)

def render_user_input_prompt():
    theme = JARVISTheme.get()
    return Text(" \n ◈ JARVIS ", style=theme["accent"]) + Text("❯ ", style=theme["secondary"])

def show_cmd_menu():
    """Show a rich command selection menu."""
    from prompt_toolkit.shortcuts import radiolist_dialog
    from cli_completer import JarvisCompleter
    
    theme = JARVISTheme.get()
    options = [(cmd, cmd) for cmd in JarvisCompleter.COMMANDS]
    
    result = radiolist_dialog(
        title="JARVIS Operations Menu",
        text="Select a sub-system command to execute:",
        values=options,
    ).run()
    
    return result

def show_theme_menu():
    """Show a theme selection menu."""
    from prompt_toolkit.shortcuts import radiolist_dialog
    
    options = [
        ("cyberpunk", "Cyberpunk (Neon Magenta/Cyan)"),
        ("noir", "Noir (Monochrome/High Contrast)"),
        ("emerald", "Emerald (Green Matrix)"),
        ("ocean", "Ocean (Deep Blue)"),
    ]
    
    result = radiolist_dialog(
        title="Visual Profile Configuration",
        text="Select terminal aesthetic:",
        values=options,
    ).run()
    
    if result:
        JARVISTheme.set(result)
        console.clear()
        render_banner()
        console.print(f"[bold {JARVISTheme.get()['success']}]Visual profile updated to: {result.upper()}[/]")
    
    return result

def print_ai_reply(text: str):
    """Render AI responses with specific padding and styling."""
    theme = JARVISTheme.get()
    # Handle markdown if needed, for now just a nice panel
    content = Text(text, style=theme["primary"])
    panel = Panel(
        content,
        title="[bold magenta]JARVIS[/]",
        title_align="left",
        border_style=theme["border"],
        padding=(1, 2)
    )
    console.print(panel)

def print_system_msg(text: str, type: str = "info"):
    theme = JARVISTheme.get()
    color = theme.get(type, theme["primary"])
    prefix_unicode = {
        "success": "✓",
        "error": "✖",
        "warning": "⚠",
        "info": "ℹ"
    }
    prefix_ascii = {
        "success": "+",
        "error": "x",
        "warning": "!",
        "info": "i"
    }
    try:
        prefix = prefix_unicode.get(type, ">")
        console.print(f"[{color}]{prefix} {text}[/]")
    except UnicodeEncodeError:
        prefix = prefix_ascii.get(type, ">")
        try:
            console.print(f"[{color}]{prefix} {text}[/]")
        except UnicodeEncodeError:
            print(f"[{type.upper()}] {text}")

def render_step_progress(steps: list[str]):
    """Animate agent reasoning steps."""
    theme = JARVISTheme.get()
    with Progress(
        SpinnerColumn(spinner_name="dots12", style=theme["accent"]),
        TextColumn("[{task.description}]", style=theme["primary"]),
        BarColumn(bar_width=20, style=theme["secondary"], complete_style=theme["success"]),
        TaskProgressColumn(),
        transient=True,
    ) as progress:
        for i, step in enumerate(steps):
            task = progress.add_task(description=step, total=100)
            # Simulate work
            for _ in range(20):
                time.sleep(0.02)
                progress.update(task, advance=5)
