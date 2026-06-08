"""Terminal presentation helpers for the JARVIS CLI experience."""
from __future__ import annotations

import itertools
import os
import sys
import time
from dataclasses import dataclass
from typing import Iterable

from cli_utils import colorize

_ASCII_TRANSLATION = str.maketrans(
    {
        "·": ".",
        "✦": "*",
        "✧": "*",
        "◇": "<>",
        "◈": "<>",
        "◆": "#",
        "✓": "OK",
        "●": "*",
        "○": "o",
        "┌": "+",
        "┐": "+",
        "┘": "+",
        "└": "+",
        "─": "-",
        "│": "|",
        "▁": "_",
        "▃": "_",
        "▅": "=",
        "▇": "#",
        "◜": "/",
        "◝": "\\",
        "◞": "\\",
        "◟": "/",
        "╳": "X",
    }
)


@dataclass(frozen=True)
class AgentCard:
    name: str
    role: str
    description: str
    color: str
    prompt: str
    spinner: tuple[str, ...]


AGENT_CARDS: tuple[AgentCard, ...] = (
    AgentCard("MAESTRO", "orchestrator", "Routes every task to the right agent", "magenta", "How does the MAESTRO orchestrator route tasks between Jarvis agents in the CLI?", ("◇", "◈", "◆", "◈")),
    AgentCard("NEXUS", "research", "Deep research, synthesis, intel briefs", "blue", "How does NEXUS deep research work in Jarvis CLI?", ("·", "o", "O", "o")),
    AgentCard("FORGE", "code", "Code gen, debug, refactor, docs", "yellow", "How does FORGE code generation work in Jarvis CLI?", ("┌", "┐", "┘", "└")),
    AgentCard("ORACLE", "planning", "Goal plans, task decomposition", "green", "How does ORACLE goal planning work in Jarvis CLI?", ("1", "2", "3", "4")),
    AgentCard("CIPHER", "security", "Security audit, threat model", "red", "How does CIPHER security auditing work in Jarvis CLI?", ("[", "{", "}", "]")),
    AgentCard("HERALD", "comms", "Draft messages, summarize, reply", "cyan", "How does HERALD message drafting work in Jarvis CLI?", ("<", "-", ">", "-")),
    AgentCard("ATLAS", "data", "SQL, pandas, visualization", "magenta", "How does ATLAS data analysis work in Jarvis CLI?", ("▁", "▃", "▅", "▇")),
    AgentCard("SCRIBE", "docs", "Docs, READMEs, changelogs", "dim", "How does SCRIBE technical documentation work in Jarvis CLI?", ("|", "/", "-", "\\")),
    AgentCard("SENTINEL", "monitor", "Health, diagnostics, live metrics", "green", "How does SENTINEL system health monitoring work in Jarvis CLI?", ("◜", "◝", "◞", "◟")),
)


DIAMOND_FRAMES: tuple[str, ...] = (
    "    .·✦·.\n  ·◇   ◇·\n ◆  ·J·  ◆\n  ·◇   ◇·\n    '·✦·'",
    "    .·✦·.\n  ·◈   ◈·\n ◆  ·A·  ◆\n  ·◈   ◈·\n    '·✦·'",
    "    .·✧·.\n  ·◆   ◆·\n ◇  ·R·  ◇\n  ·◆   ◆·\n    '·✧·'",
    "    .·✦·.\n  ·◇   ◇·\n ◆  ·V·  ◆\n  ·◇   ◇·\n    '·✦·'",
    "    .·✧·.\n  ·◈   ◈·\n ◇  ·I·  ◇\n  ·◈   ◈·\n    '·✧·'",
    "    .·✦·.\n  ·◆   ◆·\n ◆  ·S·  ◆\n  ·◆   ◆·\n    '·✦·'",
)

STATE_FRAMES: dict[str, tuple[str, ...]] = {
    "idle": (
        "    .·✦·.\n  ·◇   ◇·\n ◆   ·   ◆\n  ·◇   ◇·\n    '·✦·'",
        "    .·✧·.\n  ·◈   ◇·\n ◆   ·   ◆\n  ·◇   ◈·\n    '·✧·'",
        "    .·✦·.\n  ·◇   ◈·\n ◆   ·   ◆\n  ·◈   ◇·\n    '·✦·'",
        "    .·✧·.\n  ·◇   ◇·\n ◈   ·   ◈\n  ·◇   ◇·\n    '·✧·'",
    ),
    "thinking": DIAMOND_FRAMES,
    "talking": (
        "   .·✦·.\n ·◇  J  ◇·\n   '·✦·'",
        "    .·✦·.\n  ·◇   ◇·\n ◆  JAR  ◆\n  ·◇   ◇·\n    '·✦·'",
        "     .·✦·.\n   ·◇   ◇·\n  ◆ JARVIS ◆\n   ·◇   ◇·\n     '·✦·'",
        "    .·✦·.\n  ·◇   ◇·\n ◆  JAR  ◆\n  ·◇   ◇·\n    '·✦·'",
    ),
    "error": (
        "    .·╳·.\n  ·◇ X ◇·\n ◆  ERR  ◆\n  ·◇ X ◇·\n    '·╳·'",
        "    .·╳·.\n  ·╳ X ╳·\n ╳  ERR  ╳\n  ·╳ X ╳·\n    '·╳·'",
    ),
    "success": (
        "    .·✦·.\n  ·◇ OK ◇·\n ◆  ✓✓✓  ◆\n  ·◇ OK ◇·\n    '·✦·'",
        "  ✦ .·✦·. ✦\n  ·◇ OK ◇·\n◆  READY  ◆\n  ·◇ OK ◇·\n  ✦ '·✦·' ✦",
    ),
}

BOOT_LINES: tuple[tuple[str, str], ...] = (
    ("  ┌─ jarvis v2.0 ─────────────────────────────┐", "blue"),
    ("  │  AI Operating System  ·  9 agents online   │", "blue"),
    ("  └───────────────────────────────────────────┘", "blue"),
    ("", "dim"),
    ("  ✦ MAESTRO   orchestrator    [ready]", "magenta"),
    ("  ✦ NEXUS     research        [ready]", "blue"),
    ("  ✦ FORGE     code            [ready]", "yellow"),
    ("  ✦ ORACLE    planning        [ready]", "green"),
    ("  ✦ CIPHER    security        [ready]", "red"),
    ("  ✦ HERALD    comms           [ready]", "cyan"),
    ("  ✦ ATLAS     data            [ready]", "magenta"),
    ("  ✦ SCRIBE    docs            [ready]", "dim"),
    ("  ✦ SENTINEL  monitor         [ready]", "green"),
    ("", "dim"),
    ("  60 tools · 35 commands · plugins: terminal-ready", "dim"),
    ("  jarvis> _", "green"),
)

CONTROL_LOOP_PHASES: tuple[str, ...] = ("Interpret", "Plan", "Build", "Validate", "Check", "Fix")


def terminal_supports_animation() -> bool:
    return bool(sys.stdout.isatty() and os.environ.get("TERM") != "dumb")


def _terminal_supports_unicode() -> bool:
    encoding = (getattr(sys.stdout, "encoding", None) or "").lower()
    return "utf" in encoding


def _safe(text: str) -> str:
    if _terminal_supports_unicode():
        return text
    return text.translate(_ASCII_TRANSLATION)


def _print(text: str = "") -> None:
    print(_safe(text))


def _sleep(seconds: float, animated: bool) -> None:
    if animated and seconds > 0:
        time.sleep(seconds)


def render_boot_screen(*, animated: bool = True, delay: float = 0.035) -> None:
    """Render the diamond mascot boot screen."""
    animated = animated and terminal_supports_animation()
    _print()
    _print(colorize("Boot screen - diamond mascot", "dim"))
    _print(colorize("+------------------------------------------------------------+", "blue"))
    _print(colorize("| jarvis - terminal - 96x28                                  |", "blue"))
    _print(colorize("+------------------------------------------------------------+", "blue"))
    _print()

    mascot_lines = DIAMOND_FRAMES[-1].splitlines()
    if animated:
        for frame in DIAMOND_FRAMES:
            sys.stdout.write("\x1b[?25l")
            sys.stdout.write("\r" + _safe(colorize(frame.replace("\n", "\n"), "blue")))
            sys.stdout.flush()
            _sleep(delay * 4, animated)
            sys.stdout.write("\x1b[2K\r")
        sys.stdout.write("\x1b[?25h")

    for index, (line, color) in enumerate(BOOT_LINES):
        mascot = mascot_lines[index] if index < len(mascot_lines) else " " * 13
        _print(f"{colorize(mascot, 'blue')}  {colorize(line, color)}")
        _sleep(delay, animated)
    _print()


def render_agents() -> None:
    _print(colorize("9 agents - live in your terminal", "cyan"))
    _print("-" * 88)
    for agent in AGENT_CARDS:
        _print(
            f"{colorize(agent.name.ljust(10), agent.color)} "
            f"{agent.role.ljust(13)} "
            f"{agent.description}"
        )
    _print()
    _print("Run an agent:")
    _print("  jarvis agent run FORGE \"refactor cli_commands.py\"")
    _print("  jarvis nexus \"research local model serving options\"")


def render_design_plan() -> None:
    _print(colorize("CLI experience design", "cyan"))
    _print("-" * 88)
    sections = (
        ("Diamond mascot", "idle shimmer, thinking rotate, talking pulse, error crack, success burst"),
        ("prompt_toolkit shell", "agent autocomplete, slash commands, history search, streamed replies"),
        ("Textual dashboard", "agent status, live log, metrics, task queue"),
        ("Per-agent spinners", "unique action spinner for every JARVIS specialist"),
        ("Control loop", "Interpret -> Plan -> Build -> Validate -> Check -> Fix"),
        ("Model HUD", "download progress, Ollama/vLLM status, active model badge"),
    )
    for title, body in sections:
        _print(f"{colorize(title.ljust(22), 'blue')} {body}")
    _print()
    _print(colorize("Build phases", "cyan"))
    phases = (
        ("week 1", "Diamond mascot, boot sequence, ANSI color system"),
        ("week 2", "REPL routing display, agent completions, streaming typewriter output"),
        ("week 3", "Textual dashboard panels with keyboard navigation"),
        ("week 4", "Control-loop visualizer and model serving HUD"),
        ("week 5", "Plugin browser, skills hot-reload, sync and sandbox panels"),
    )
    for tag, body in phases:
        _print(f"{colorize(tag.ljust(8), 'green')} {body}")


def render_state_frames(state: str = "all") -> None:
    names: Iterable[str] = STATE_FRAMES if state == "all" else (state,)
    for name in names:
        frames = STATE_FRAMES.get(name)
        if not frames:
            _print(f"Unknown state: {name}")
            continue
        _print(colorize(f"{name} state", "cyan"))
        for i, frame in enumerate(frames, start=1):
            _print(colorize(f"frame {i}", "dim"))
            _print(colorize(frame, "blue" if name != "error" else "red"))
        _print()


def render_control_loop(active: str | None = None) -> None:
    active_normalized = (active or "").strip().lower()
    parts = []
    for phase in CONTROL_LOOP_PHASES:
        marker = "●" if phase.lower() == active_normalized else "○"
        color = "green" if marker == "●" else "dim"
        parts.append(colorize(f"{marker} {phase}", color))
    _print(" -> ".join(parts))


def render_routing_decision(agent: str, reason: str = "selected by MAESTRO") -> None:
    card = next((item for item in AGENT_CARDS if item.name == agent.upper()), None)
    color = card.color if card else "green"
    role = card.role if card else "agent"
    _print(f"{colorize('MAESTRO route', 'magenta')}: {colorize(agent.upper(), color)} ({role}) - {reason}")
    render_control_loop("Build")


def spinner_for(agent: str):
    card = next((item for item in AGENT_CARDS if item.name == agent.upper()), None)
    frames = card.spinner if card else ("|", "/", "-", "\\")
    return itertools.cycle(frames)
