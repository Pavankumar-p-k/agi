"""jarvis CLI - Command line interface for JARVIS."""
from __future__ import annotations

import asyncio
import sys
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.agent_loop import stream_agent_loop
from core.configuration import configuration
from core.build.service import build_service
from core.pipeline import process_message
from core.pipeline.messages import Request

console = Console()


@click.group(invoke_without_command=True)
@click.option("--version", is_flag=True, help="Show version")
@click.pass_context
def cli(ctx: click.Context, version: bool) -> None:
    """JARVIS - Your AI Life Operating System."""
    if version:
        console.print("[bold cyan]JARVIS[/bold cyan] v0.1.0")
        return
    if ctx.invoked_subcommand is None:
        console.print(Panel.fit(
            "[bold cyan]JARVIS[/bold cyan] - AI Life Operating System\n"
            "Run [bold]jarvis --help[/bold] for commands",
            border_style="cyan"
        ))


@cli.command()
@click.argument("message", required=True)
@click.option("--model", "-m", default=None, help="Model to use")
@click.option("--session", "-s", default=None, help="Session ID")
@click.option("--stream/--no-stream", default=True, help="Stream response")
def chat(message: str, model: Optional[str], session: Optional[str], stream: bool) -> None:
    """Chat with JARVIS."""
    async def _chat() -> None:
        if stream:
            async for event in stream_agent_loop(
                endpoint_url=configuration.get("ollama.base_url", "http://localhost:11434"),
                model=model or configuration.get("llm.chat_model", "qwen2.5:7b"),
                messages=[{"role": "user", "content": message}],
                session_id=session,
            ):
                if event.startswith("data: "):
                    try:
                        import json
                        data = json.loads(event[6:])
                        if data.get("type") == "delta" and data.get("delta"):
                            console.print(data["delta"], end="")
                        elif data == "[DONE]":
                            console.print()
                    except Exception:
                        pass
        else:
            req = Request(text=message, transport="cli", session_id=session)
            resp = await process_message(req)
            if resp.error:
                console.print(f"[red]Error: {resp.error}[/red]")
            else:
                console.print(resp.text)

    asyncio.run(_chat())


@cli.command()
@click.argument("goal", required=True)
@click.option("--workspace", "-w", default=None, help="Workspace path")
def build(goal: str, workspace: Optional[str]) -> None:
    """Start an autonomous build."""
    async def _build() -> None:
        entry = build_service.enqueue(goal, workspace=workspace)
        console.print(f"[green]Build queued:[/green] {entry.name}")
        console.print(f"Goal: {goal}")

    asyncio.run(_build())


@cli.command()
def builds() -> None:
    """List all build projects."""
    projects = build_service.list_all()
    if not projects:
        console.print("[yellow]No builds found[/yellow]")
        return

    table = Table(title="Build Projects")
    table.add_column("Name", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Goal", style="white")
    table.add_column("Priority", style="yellow")

    for p in projects:
        table.add_row(p["name"], p["status"], p["goal"][:50], str(p.get("priority", 1)))

    console.print(table)


@cli.command()
@click.argument("name", required=True)
def cancel(name: str) -> None:
    """Cancel a build."""
    if build_service.cancel(name):
        console.print(f"[green]Cancelled:[/green] {name}")
    else:
        console.print(f"[red]Not found:[/red] {name}")


@cli.command()
@click.argument("name", required=True)
def resume(name: str) -> None:
    """Resume a paused build."""
    if build_service.resume(name):
        console.print(f"[green]Resumed:[/green] {name}")
    else:
        console.print(f"[red]Cannot resume:[/red] {name}")


@cli.command()
def status() -> None:
    """Show system status."""
    console.print(Panel("[bold cyan]JARVIS System Status[/bold cyan]", border_style="cyan"))

    # Config status
    console.print("\n[bold]Configuration:[/bold]")
    console.print(f"  Chat model: {configuration.get('llm.chat_model', 'N/A')}")
    console.print(f"  Code model: {configuration.get('llm.code_model', 'N/A')}")
    console.print(f"  Dev mode: {configuration.get('server.dev_mode', False)}")

    # Pipeline status
    from core.pipeline import get_pipeline
    pipeline = get_pipeline()
    console.print(f"\n[bold]Pipeline:[/bold] {len(pipeline.stages)} stages")
    for stage in pipeline.stages:
        console.print(f"  - {stage.name}")


if __name__ == "__main__":
    cli()