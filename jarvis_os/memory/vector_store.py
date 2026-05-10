from __future__ import annotations

import json
import os
from collections import Counter
import re
from typing import Any


def _tokenize(text: str) -> Counter[str]:
    words = re.findall(r"[A-Za-z0-9_:-]+", text.lower())
    return Counter(words)


class VectorStore:
    def __init__(self, persist_path: str = "vector_store.json") -> None:
        self.persist_path = persist_path
        self._documents: list[dict[str, Any]] = []
        self._load()

    def add(self, document: dict[str, Any]) -> None:
        payload = dict(document)
        payload["_tokens"] = _tokenize(str(document.get("text", "")))
        self._documents.append(payload)
        self._save()

    def search(
        self,
        query: str,
        top_k: int = 5,
        *,
        kinds: list[str] | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        query_tokens = _tokenize(query)
        scored: list[tuple[int, dict[str, Any]]] = []
        allowed_kinds = set(kinds or [])
        expected_metadata = metadata_filter or {}
        for document in self._documents:
            if allowed_kinds and document.get("kind") not in allowed_kinds:
                continue
            metadata = document.get("metadata", {})
            if expected_metadata and not _metadata_matches(metadata, expected_metadata):
                continue
            score = sum((query_tokens & document["_tokens"]).values())
            if score:
                scored.append((score, document))
        scored.sort(key=lambda item: item[0], reverse=True)
        results = [
            {key: value for key, value in document.items() if key != "_tokens"} | {"score": score}
            for score, document in scored[:top_k]
        ]
        # Compress context before use
        for result in results:
            if "text" in result and len(result["text"]) > 500:
                result["text"] = result["text"][:500] + "..."
        return results

    def _load(self) -> None:
        if os.path.exists(self.persist_path):
            try:
                with open(self.persist_path, "r") as f:
                    self._documents = json.load(f)
            except:
                self._documents = []

    def _save(self) -> None:
        try:
            with open(self.persist_path, "w") as f:
                json.dump(self._documents, f)
        except OSError as exc:
            raise RuntimeError(f"Failed to persist vector store: {exc}") from exc


def _metadata_matches(metadata: dict[str, Any], expected: dict[str, Any]) -> bool:
    for key, value in expected.items():
        actual = metadata.get(key)
        if key == "agent_scope":
            if actual not in {None, "", value}:
                return False
            continue
        if actual != value:
            return False
    return True
