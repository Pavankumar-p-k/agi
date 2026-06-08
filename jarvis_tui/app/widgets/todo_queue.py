from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, Static, ListView, ListItem
from textual.containers import Vertical
from textual.reactive import reactive

class TodoItem(ListItem):
    def __init__(self, todo_text: str, todo_status: str = "todo", **kwargs):
        super().__init__(**kwargs)
        self.todo_text = todo_text
        self.todo_status = todo_status # todo, doing, done

    def compose(self) -> ComposeResult:
        icon = "○"
        if self.todo_status == "doing": icon = "▶"
        elif self.todo_status == "done": icon = "✓"
        yield Label(f"{icon} {self.todo_text}")

class TodoQueue(Widget):
    """
    Live-editable task list for JARVIS agents.
    """
    def compose(self) -> ComposeResult:
        yield Label("TODO QUEUE")
        yield ListView(id="todo-list")

    def on_mount(self) -> None:
        # Start empty - wait for backend sync
        pass

    def add_task(self, task: str) -> None:
        lst = self.query_one("#todo-list", ListView)
        lst.append(TodoItem(task))

    def complete_task(self, index: int) -> None:
        lst = self.query_one("#todo-list", ListView)
        if 0 <= index < len(lst.children):
            item = lst.children[index]
            item.todo_status = "done"
            item.query_one(Label).update(f"✓ {item.todo_text}")
