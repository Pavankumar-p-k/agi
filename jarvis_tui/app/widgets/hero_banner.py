from __future__ import annotations

import asyncio
from datetime import datetime
from textual.app import ComposeResult
from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text
from rich.panel import Panel
from rich.align import Align

class HeroBanner(Widget):
    """
    Hero Banner with ASCII JARVIS and animated orb.
    """
    status_tagline = reactive("Agent Commander v2 // online")
    orb_frame = reactive(0)
    mood = reactive("idle") # idle, thinking, done, error
    scan_pos = reactive(-1)
    
    ORB_CHARS = {
        "idle": ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"],
        "thinking": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
        "done": ["⠿", "⠷", "⠦", "⠖", "⠒", "⠐", "⠒", "⠖", "⠦", "⠷"],
        "error": ["⣷", "⣯", "⣟", "⡿", "⢿", "⣻", "⣽", "⣾"]
    }
    
    MOOD_COLORS = {
        "idle": "cyan",
        "thinking": "amber", # rich doesn't have amber, using yellow
        "done": "green",
        "error": "red"
    }

    TAGLINES = [
        "Agent Commander v2 // online",
        "4 agents awake // watching",
        "AI OS // ready"
    ]

    ASCII_LINES = [
        "     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗",
        "     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝",
        "     ██║███████║██████╔╝██║   ██║██║███████╗",
        "██   ██║██╔══██║██╔══██║╚██╗ ██╔╝██║╚════██║",
        "╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║"
    ]

    def on_mount(self) -> None:
        self.set_interval(0.1, self.update_orb)
        self.set_interval(4.0, self.rotate_tagline)
        self.set_interval(4.0, self.trigger_scanline)
        self.start_time = datetime.now()

    def update_orb(self) -> None:
        frames = self.ORB_CHARS.get(self.mood, self.ORB_CHARS["idle"])
        self.orb_frame = (self.orb_frame + 1) % len(frames)

    def rotate_tagline(self) -> None:
        idx = self.TAGLINES.index(self.status_tagline)
        self.status_tagline = self.TAGLINES[(idx + 1) % len(self.TAGLINES)]

    def trigger_scanline(self) -> None:
        self.scan_pos = 0
        self.run_worker(self.animate_scanline())

    async def animate_scanline(self) -> None:
        width = len(self.ASCII_LINES[0])
        for x in range(width + 5):
            self.scan_pos = x
            await asyncio.sleep(0.05)
        self.scan_pos = -1

    def render(self) -> Panel:
        color = self.MOOD_COLORS.get(self.mood, "cyan")
        if color == "amber": color = "bright_yellow"
        
        frames = self.ORB_CHARS.get(self.mood, self.ORB_CHARS["idle"])
        orb = Text(frames[self.orb_frame % len(frames)], style=f"{color} bold")
        
        # Build ASCII art with scanline effect
        content = Text()
        content.append(orb)
        content.append("\n")
        
        for line in self.ASCII_LINES:
            line_text = Text()
            for i, char in enumerate(line):
                # Scanline wave effect (pulse color)
                if self.scan_pos != -1 and abs(i - self.scan_pos) < 3:
                    line_text.append(char, style="cyan bold")
                else:
                    line_text.append(char, style="blue bold")
            content.append(line_text)
            content.append("\n")
        
        content.append(f"  {self.status_tagline}", style="italic dim")
        
        return Panel(
            Align.center(content),
            border_style="blue",
            padding=(0, 1)
        )
