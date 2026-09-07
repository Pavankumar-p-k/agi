"""Diagnostics and boot sequence reporting."""
from contextlib import contextmanager
from pathlib import Path


class BootStep:
    def __init__(self, name: str):
        self.name = name
        self.status = "ok"
        self.detail = ""
        self.error = ""
        self.suggestion = ""


class BootSequence:
    def __init__(self, title: str = ""):
        self.title = title
        self.steps: list[BootStep] = []

    @contextmanager
    def step(self, name: str):
        step_obj = BootStep(name)
        self.steps.append(step_obj)
        try:
            yield step_obj
        except Exception as e:
            step_obj.status = "failed"
            step_obj.error = str(e)
            raise

    def print_report(self) -> None:
        pass

    def ok(self) -> bool:
        return all(s.status == "ok" for s in self.steps)


def read_tail(path: Path | str, n_lines: int = 40) -> str:
    try:
        p = Path(path)
        if not p.exists():
            return ""
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n_lines:])
    except Exception:
        return ""
