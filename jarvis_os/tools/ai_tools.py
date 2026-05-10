from __future__ import annotations

import re
from pathlib import Path

from ..contracts import ToolSpec


def register_ai_tools(registry) -> None:
    registry.register(
        ToolSpec("summarize_text", "Summarize input text.", ["text"], category="general", read_only=True),
        lambda text, **_: _summarize_text(registry, text),
    )
    registry.register(
        ToolSpec("classify_text", "Classify text into provided labels.", ["text", "labels"], category="general", read_only=True),
        lambda text, labels=None, **_: _classify_text(text, labels or []),
    )
    registry.register(
        ToolSpec("extract_entities", "Extract simple entities from text.", ["text"], category="general", read_only=True),
        lambda text, **_: _extract_entities(text),
    )
    registry.register(
        ToolSpec("generate_documentation", "Generate a documentation summary for a file or folder.", ["path"], category="general", read_only=True),
        lambda path=".", **_: _generate_documentation(path),
    )


def _summarize_text(registry, text: str) -> dict:
    clean = re.sub(r"\s+", " ", text).strip()
    lowered = clean.lower()
    if lowered in {"hi", "hello", "hey", "yo", "hi jarvis", "hello jarvis", "hey jarvis"}:
        return {"summary": "Hello. What do you want me to do?"}
    if lowered in {"who are you", "who are u", "who r u"}:
        return {"summary": "I'm JARVIS, your AI assistant."}
    response = registry.models.generate(
        prompt=f"Summarize this text in 3 short sentences:\n{text[:6000]}",
        task="analysis",
        system="Be concise and concrete.",
    )
    if response.get("ok") and response.get("response"):
        return {"summary": response["response"].strip()}
    return {"summary": clean[:300] + ("..." if len(clean) > 300 else "")}


def _classify_text(text: str, labels: list[str]) -> dict:
    lowered = text.lower()
    scores = {label: 0 for label in labels}
    for label in labels:
        scores[label] = lowered.count(label.lower())
    best = max(scores, key=scores.get) if scores else "unknown"
    return {"label": best, "scores": scores}


def _extract_entities(text: str) -> dict:
    urls = re.findall(r"https?://\S+", text)
    emails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    names = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text)
    return {"urls": urls, "emails": emails, "names": names[:20]}


def _generate_documentation(path: str) -> dict:
    target = Path(path).expanduser().resolve()
    if target.is_file():
        text = target.read_text(encoding="utf-8", errors="replace")
        return {
            "path": str(target),
            "documentation": f"{target.name}: {len(text.splitlines())} line(s), {len(text)} character(s).",
        }
    files = [item for item in target.rglob("*") if item.is_file()]
    return {
        "path": str(target),
        "documentation": f"{target.name}: {len(files)} file(s) discovered.",
        "sample_files": [str(item) for item in files[:20]],
    }
