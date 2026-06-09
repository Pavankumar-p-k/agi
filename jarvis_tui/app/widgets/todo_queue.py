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

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView


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
