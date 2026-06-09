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
import asyncio
import logging
import re
from contextvars import ContextVar
from pathlib import Path

# Try to import py_compile for edit verification
try:
    import py_compile
except ImportError:
    py_compile = None

from datetime import UTC

from core.tools._tool_utils import MAX_READ_CHARS, _parse_tool_args

_DIFF_HUNK_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*?(?:\n|$)",
    re.MULTILINE,
)

logger = logging.getLogger(__name__)


# Active document state — use ContextVar for async/thread safety

_active_document_id: ContextVar[str | None] = ContextVar("_active_document_id", default=None)
_active_model: ContextVar[str | None] = ContextVar("_active_model", default=None)


def set_active_document(doc_id: str | None):
    _active_document_id.set(doc_id)


def set_active_model(model: str | None):
    _active_model.set(model)


def get_active_document():
    return _active_document_id.get().get()


def clear_active_document(doc_id: str | None = None) -> bool:
    current = _active_document_id.get()
    if doc_id is None or current == doc_id:
        _active_document_id.set(None)
        return True
    return False


def _owned_document_query(query, Document, owner: str | None):
    if owner is None:
        from sqlalchemy import false
        return query.filter(false())
    return query.filter(Document.owner == owner)


def _get_owned_document(db, Document, doc_id: str, owner: str | None, active_only: bool = False):
    q = db.query(Document).filter(Document.id == doc_id)
    if active_only:
        q = q.filter(Document.is_active == True)
    q = _owned_document_query(q, Document, owner)
    return q.first()


def _most_recent_owned_document(db, Document, owner: str | None, active_only: bool = False):
    q = db.query(Document)
    if active_only:
        q = q.filter(Document.is_active == True)
    q = _owned_document_query(q, Document, owner)
    return q.order_by(Document.updated_at.desc()).first()


# Document helpers

def _sniff_doc_language(text: str) -> str:
    import json as _json
    import re as _re2
    s = (text or "").strip()
    if not s:
        return "markdown"
    head = s[:600]
    hl = head.lower()
    if _looks_like_email_document(s):
        return "email"
    if "<svg" in hl:
        return "svg"
    if hl.startswith("<?xml"):
        return "xml"
    if (hl.startswith("<!doctype html") or hl.startswith("<html")
            or _re2.search(r"<(div|body|head|p|span|table|button|h[1-6]|ul|ol|li|img)\b", hl)):
        return "html"
    if s[0] in "{[":
        try:
            _json.loads(s)
            return "json"
        except Exception as _e:
            logger.debug("_detect_content_type json parse failed: %s", _e)
    first = s.split("\n", 1)[0].strip().lower()
    if first.startswith("#!"):
        return "python" if "python" in first else "bash"
    if _re2.search(r"(?m)^\s*(def \w|class \w|import \w|from \w[\w.]* import )", s):
        return "python"
    if _re2.search(r"(?m)^\s*(function \w|const \w|let \w|export |import .* from )", s):
        return "javascript"
    if _re2.search(r"(?mi)^\s*(select .* from |create table |insert into |update \w)", s):
        return "sql"
    if _re2.search(r"(?m)^[.#]?[\w-]+\s*\{[^{}]*:[^{}]*;", s):
        return "css"
    return "markdown"


def _looks_like_email_document(text: str = "", title: str = "") -> bool:
    import re as _re
    title_l = (title or "").strip().lower()
    if title_l in {"new email", "new mail", "new message"}:
        return True
    s = (text or "").lstrip()
    if "\n---\n" in s and _re.search(r"(?im)^To:\s*", s) and _re.search(r"(?im)^Subject:\s*", s):
        return True
    return bool(_re.search(r"(?im)^To:\s*", s) and _re.search(r"(?im)^Subject:\s*", s))


def _coerce_email_document_content(existing: str, incoming: str) -> str:
    import re as _re
    old = existing or ""
    new = (incoming or "").strip()
    if "\n---\n" in new:
        return new
    header = old.split("\n---\n", 1)[0] if "\n---\n" in old else "To: \nSubject: "
    if _looks_like_email_document(new):
        lines = new.splitlines()
        last_header_idx = -1
        header_re = _re.compile(r"^(To|Cc|Bcc|Subject|In-Reply-To|References|X-Source-UID|X-Source-Folder|X-Attachments):", _re.I)
        for i, line in enumerate(lines):
            if header_re.match(line.strip()):
                last_header_idx = i
        body_lines = lines[last_header_idx + 1:] if last_header_idx >= 0 else lines
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
        body = "\n".join(body_lines).strip()
    else:
        body = new
    return header.rstrip() + "\n---\n" + body


# Create document

def _do_create_document_sync(content_block: str, session_id: str | None = None, owner: str | None = None) -> dict:
    import re as _re
    import uuid

    from core.database_models import Document, DocumentVersion, SessionLocal
    from core.database_models import Session as DbSession

    raw = content_block or ""
    _KNOWN_LANGS = {
        "python", "javascript", "typescript", "html", "css", "markdown", "json",
        "yaml", "bash", "sql", "rust", "go", "java", "c", "cpp", "xml", "toml",
        "ini", "ruby", "php", "csv", "email", "text", "plain", "svg",
    }

    title = None
    language = None
    content = None
    mt = _re.search(r"<title>\s*(.*?)\s*</title>", raw, _re.DOTALL | _re.IGNORECASE)
    ml = _re.search(r"<language>\s*(.*?)\s*</language>", raw, _re.DOTALL | _re.IGNORECASE)
    mc = _re.search(r"<content>\s*(.*?)\s*</content>", raw, _re.DOTALL | _re.IGNORECASE)
    if mt or mc:
        title = mt.group(1).strip() if mt else None
        language = ml.group(1).strip().lower() if ml else None
        content = mc.group(1) if mc else None

    if title is None or content is None:
        cleaned = _re.sub(r"</?(?:title|language|content)>", "", raw)
        lines = cleaned.strip().split("\n")
        if title is None:
            title = lines[0].strip() if lines else "Untitled"
            lines = lines[1:]
        if language is None and lines:
            candidate = lines[0].strip().lower()
            if candidate and len(candidate) < 20 and " " not in candidate and candidate in _KNOWN_LANGS:
                language = candidate
                lines = lines[1:]
        if content is None:
            content = "\n".join(lines)

    if language and language not in _KNOWN_LANGS:
        language = None
    if not language:
        language = _sniff_doc_language(content)
    if _looks_like_email_document(content, title):
        language = "email"

    if not title:
        title = "Untitled"

    if not session_id:
        return {"error": "No session context for document creation"}

    db = SessionLocal()
    try:
        doc_id = str(uuid.uuid4())
        ver_id = str(uuid.uuid4())

        _sess = db.query(DbSession).filter(DbSession.id == session_id).first()
        if owner is not None and (not _sess or _sess.owner != owner):
            return {"error": "Cannot create document in another user's session"}
        _owner = _sess.owner if _sess else None

        doc = Document(
            id=doc_id,
            session_id=session_id,
            title=title,
            language=language,
            current_content=content,
            version_count=1,
            is_active=True,
            owner=_owner,
        )
        ver = DocumentVersion(
            id=ver_id,
            document_id=doc_id,
            version_number=1,
            content=content,
            summary=f"Created by {_active_model.get() or 'AI'}",
            source="ai",
        )
        db.add(doc)
        db.add(ver)
        db.commit()

        set_active_document(doc_id)
        try:
            from core.event_bus import fire_event
            fire_event("document_created", _owner)
        except Exception as _e:
            logger.debug("document_created event dispatch failed: %s", _e)

        return {
            "action": "create",
            "doc_id": doc_id,
            "title": title,
            "language": language,
            "content": content,
            "version": 1,
        }
    except Exception as e:
        db.rollback()
        return {"error": f"Failed to create document: {e}"}
    finally:
        db.close()


async def do_create_document(content_block: str, session_id: str | None = None, owner: str | None = None) -> dict:
    return await asyncio.to_thread(_do_create_document_sync, content_block, session_id, owner)


# Suggest blocks

def parse_suggest_blocks(text: str) -> list[dict]:
    results = []
    pattern = re.compile(
        r"<<<FIND>>>\s*(.*?)\s*<<<SUGGEST>>>\s*(.*?)\s*<<<REASON>>>\s*(.*?)\s*<<<END>>>",
        re.DOTALL,
    )
    for m in pattern.finditer(text):
        results.append({
            "find": m.group(1).strip(),
            "suggest": m.group(2).strip(),
            "reason": m.group(3).strip(),
        })
    return results


# Update document

def _do_update_document_sync(content: str, doc_id: str | None = None, owner: str | None = None) -> dict:
    import uuid
    from datetime import datetime

    from core.database_models import Document, DocumentVersion, SessionLocal

    target_id = doc_id or _active_document_id.get()
    if not target_id:
        return {"error": "No active document to update"}

    stripped = content.strip()
    if not stripped:
        return {"error": "No content provided for update_document"}

    db = SessionLocal()
    try:
        doc = _get_owned_document(db, Document, target_id, owner)
        if not doc:
            return {"error": f"Document {target_id} not found"}

        ver_id = str(uuid.uuid4())
        ver = DocumentVersion(
            id=ver_id,
            document_id=target_id,
            version_number=doc.version_count + 1,
            content=doc.current_content,
            summary=f"Updated by {_active_model.get() or 'AI'}",
            source="ai",
        )
        doc.current_content = stripped
        doc.version_count = doc.version_count + 1
        doc.updated_at = datetime.utcnow()
        db.add(ver)
        db.commit()

        return {
            "action": "update",
            "doc_id": target_id,
            "title": doc.title,
            "version": doc.version_count,
            "size": len(stripped),
        }
    finally:
        db.close()


async def do_update_document(content: str, doc_id: str | None = None, owner: str | None = None) -> dict:
    return await asyncio.to_thread(_do_update_document_sync, content, doc_id, owner)


# Suggest document

def _do_suggest_document_sync(content: str, doc_id: str | None = None, owner: str | None = None) -> dict:
    from core.database_models import Document, SessionLocal

    target_id = doc_id or _active_document_id.get()
    if not target_id:
        return {"error": "No active document to suggest on"}

    suggestions = parse_suggest_blocks(content)
    if not suggestions:
        return {"error": "No valid <<<FIND>>>...<<<SUGGEST>>>...<<<REASON>>>...<<<END>>> blocks found"}

    db = SessionLocal()
    try:
        doc = _get_owned_document(db, Document, target_id, owner)
        if not doc:
            return {"error": f"Document {target_id} not found"}

        valid = []
        for s in suggestions:
            if s["find"] in doc.current_content:
                valid.append(s)
            else:
                logger.warning(f"suggest_document: FIND text not found, skipping: {s['find'][:80]!r}")

        if not valid:
            return {"error": "No suggestions matched the document content"}

        return {
            "action": "suggest",
            "doc_id": target_id,
            "suggestions": valid,
            "count": len(valid),
        }
    finally:
        db.close()


async def do_suggest_document(content: str, doc_id: str | None = None, owner: str | None = None) -> dict:
    return await asyncio.to_thread(_do_suggest_document_sync, content, doc_id, owner)


# Edit blocks

_DIFF_HUNK_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*?(?:\n|$)",
    re.MULTILINE,
)


def _apply_unified_diff(current: str, diff_text: str) -> tuple[str | None, str]:
    """Apply a unified diff to ``current`` text.

    Parses hunk lines maintaining interleaving order of context / removed / added.
    Verifies context lines match at the target position.
    Returns ``(new_text, error_message)``.
    """
    current = current.replace("\r\n", "\n")
    lines = current.split("\n")
    if current == "":
        lines = []
    elif current.endswith("\n"):
        lines = lines[:-1]
    hunks = []
    for m in _DIFF_HUNK_RE.finditer(diff_text):
        old_start = int(m.group(1))
        old_count = int(m.group(2)) if m.group(2) else 1

        hunk_start = m.end()
        hunk_end = _DIFF_HUNK_RE.search(diff_text, hunk_start)
        hunk_end = hunk_end.start() if hunk_end else len(diff_text)
        hunk_body = diff_text[hunk_start:hunk_end].rstrip("\n")

        # Parse hunk body preserving interleaving order
        old_lines = []    # context + removed in original order
        new_lines = []    # context + added in original order
        for hline in hunk_body.split("\n"):
            if hline.startswith("-"):
                old_lines.append(hline[1:])
            elif hline.startswith("+"):
                new_lines.append(hline[1:])
            else:
                content = hline[1:] if hline.startswith(" ") else hline
                old_lines.append(content)
                new_lines.append(content)

        if len(old_lines) != old_count:
            return None, (
                f"Hunk at line {old_start}: header says {old_count} old lines, "
                f"but found {len(old_lines)}"
            )
        hunks.append((old_start, old_count, old_lines, new_lines))

    if not hunks:
        return None, "No valid hunks found in diff"

    # Apply hunks in reverse order (bottom-up)
    for old_start, old_count, old_lines, new_lines in reversed(hunks):
        if old_count == 0:
            # Insert at beginning (old_start == 0)
            cutoff = max(0, old_start - 1)
            lines = lines[:cutoff] + new_lines + lines[cutoff:]
            continue
        if old_start - 1 > len(lines):
            return None, f"Hunk at line {old_start} past end of file ({len(lines)} lines)"
        hunk_lines = lines[old_start - 1:old_start - 1 + old_count]
        if len(hunk_lines) != len(old_lines):
            return None, (
                f"Hunk at line {old_start}: expected {len(old_lines)} lines, "
                f"got {len(hunk_lines)}"
            )
        for i, (hl, oline) in enumerate(zip(hunk_lines, old_lines)):
            if hl != oline:
                return None, (
                    f"Hunk at line {old_start}: context mismatch on line {old_start + i}. "
                    f"Expected {oline!r}, got {hl!r}"
                )
        lines = lines[:old_start - 1] + new_lines + lines[old_start - 1 + old_count:]

    return "\n".join(lines), ""


_LINE_RE = re.compile(r"^(?:L?\d+[:\s]\s*)?(.*)", re.DOTALL)


def parse_edit_blocks(text: str) -> list[dict]:
    results = []
    pattern = re.compile(
        r"<<<FIND>>>\s*(.*?)\s*<<<REPLACE>>>\s*(.*?)\s*<<<DOC_ID>>>\s*(.*?)\s*<<<END>>>"
        r"|<<<FIND>>>\s*(.*?)\s*<<<REPLACE>>>\s*(.*?)\s*<<<END>>>",
        re.DOTALL,
    )
    for m in pattern.finditer(text):
        if m.group(3) is not None:
            raw_find = m.group(1)
            raw_replace = m.group(2)
            doc_id = m.group(3).strip()
        else:
            raw_find = m.group(4)
            raw_replace = m.group(5)
            doc_id = ""
        raw_find = raw_find.strip()
        raw_replace = raw_replace.strip()
        find_m = _LINE_RE.match(raw_find)
        results.append({
            "find": raw_find,
            "replace": raw_replace,
            "doc_id": doc_id,
            "find_text": find_m.group(1).rstrip("\n\r") if find_m else raw_find.rstrip("\n\r"),
        })
    return results


def _normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n")


def _find_edit_location(
    doc_text: str, find_text: str,
) -> tuple[int | None, str]:
    """Try to locate ``find_text`` in ``doc_text``.

    Returns ``(start_index, match_type)`` where ``match_type`` is one of
    ``"exact"``, ``"normalized"``, ``"stripped"``, or ``None`` if no match found.
    """
    norm_doc = _normalize_text(doc_text)
    norm_find = _normalize_text(find_text)

    # 1) exact
    idx = norm_doc.find(norm_find)
    if idx != -1:
        return idx, "exact"

    # 2) strip trailing whitespace per line
    stripped_doc = "\n".join(l.rstrip() for l in norm_doc.split("\n"))
    stripped_find = "\n".join(l.rstrip() for l in norm_find.split("\n"))
    idx = stripped_doc.find(stripped_find)
    if idx != -1:
        return idx, "normalized"

    # 3) strip + collapse multiple spaces
    tight_doc = "\n".join(" ".join(l.split()) for l in stripped_doc.split("\n"))
    tight_find = "\n".join(" ".join(l.split()) for l in stripped_find.split("\n"))
    idx = tight_doc.find(tight_find)
    if idx != -1:
        return idx, "stripped"

    # 4) line-number-based matching — find_text starts with "L42:" or "42:"
    _line_match = re.match(r"(?:L?\d+)[:.\s]\s*", find_text)
    if _line_match:
        try:
            target_line = int(re.sub(r"[^0-9]", "", _line_match.group()))
        except (ValueError, IndexError):
            target_line = None
        if target_line and target_line <= len(norm_doc.split("\n")):
            # Try to match around that line using the normalized form
            find_no_lineno = find_text[_line_match.end():]
            idx, _ = _try_fuzzy_match(norm_doc, find_no_lineno or norm_find, target_line)
            if idx is not None:
                return idx, "fuzzy_line"

    # 5) LCS-based: find the longest contiguous common substring
    lcs_idx, _ = _longest_common_substring(norm_doc, norm_find)
    if lcs_idx is not None:
        return lcs_idx, "fuzzy_lcs"

    return None, None


def _try_fuzzy_match(doc: str, needle: str, around_line: int) -> tuple[int | None, str]:
    """Search for ``needle`` within a window around ``around_line`` (1-indexed)."""
    doc_lines = doc.split("\n")
    window = 30
    start_ln = max(0, around_line - window - 1)
    end_ln = min(len(doc_lines), around_line + window)
    for candidate in ("exact", "normalized", "stripped"):
        for ln_off in range(end_ln - start_ln):
            start_doc_line = start_ln + ln_off
            # Build substring from doc matching needle's line count
            needle_lines = needle.count("\n") + 1
            chunk = "\n".join(doc_lines[start_doc_line:start_doc_line + needle_lines])
            fn = _normalize_text(needle)
            if candidate == "exact":
                idx = chunk.find(fn)
            elif candidate == "normalized":
                chunk_n = "\n".join(l.rstrip() for l in chunk.split("\n"))
                fn_n = "\n".join(l.rstrip() for l in fn.split("\n"))
                idx = chunk_n.find(fn_n)
            else:
                chunk_t = "\n".join(" ".join(l.split()) for l in chunk.split("\n"))
                fn_t = "\n".join(" ".join(l.split()) for l in fn.split("\n"))
                idx = chunk_t.find(fn_t)
            if idx != -1:
                # Convert chunk-local offset to global doc offset
                global_offset = sum(len(l) + 1 for l in doc_lines[:start_doc_line]) + idx
                return global_offset, f"{candidate}_near_L{around_line}"
    return None, None


def _longest_common_substring(a: str, b: str) -> tuple[int | None, int]:
    """Return the start index in ``a`` of the longest common substring with ``b``.
    Uses suffix matching: find any line or significant chunk from ``b`` that
    appears in ``a``.
    """
    if not a or not b:
        return None, 0
    # Try matching each line of b independently (handles multi-line search)
    b_lines = b.split("\n")
    for line in b_lines:
        stripped = line.strip()
        if len(stripped) >= 10:
            idx = a.find(stripped)
            if idx != -1:
                return idx, len(stripped)
    # Try matching progressively smaller suffix chunks
    for chunk_len in range(len(b) - 1, 9, -1):
        for start in range(0, len(b) - chunk_len + 1):
            sub = b[start:start + chunk_len]
            idx = a.find(sub)
            if idx != -1:
                return idx, chunk_len
    return None, 0


def _apply_edit_to_text(current: str, ed: dict) -> tuple[str | None, dict]:
    """Apply a single edit dict to ``current`` text.

    Returns ``(new_text, detail)`` where ``detail`` is the per-edit
    result dict (status, find_preview, match).  If the edit cannot be
    applied ``new_text`` is ``None``.
    """
    find_text = ed["find_text"]
    idx, match_type = _find_edit_location(current, find_text)

    if idx is None and ed.get("find"):
        idx, match_type = _find_edit_location(current, ed["find"])

    if idx is None:
        preview = find_text[:80].replace("\n", "\\n")
        return None, {"status": "not_found", "find_preview": preview, "match": None}

    prep = ed.get("replace", "")
    if match_type in ("exact",):
        new_text = current[:idx] + prep + current[idx + len(find_text):]
    elif match_type in ("normalized", "fuzzy_line", "fuzzy_lcs"):
        stripped_find = "\n".join(l.rstrip() for l in _normalize_text(find_text).split("\n"))
        new_text = current[:idx] + prep + current[idx + len(stripped_find):]
    elif match_type in ("stripped",):
        stripped_find = "\n".join(l.rstrip() for l in _normalize_text(find_text).split("\n"))
        tight_find = "\n".join(" ".join(l.split()) for l in stripped_find.split("\n"))
        new_text = current[:idx] + prep + current[idx + len(tight_find):]
    else:
        return None, {"status": "unknown_match", "find_preview": find_text[:80].replace("\n", "\\n")}

    return new_text, {"status": "ok", "find_preview": find_text[:80].replace("\n", "\\n"), "match": match_type}


# Edit document

def _verify_document_content(title: str, content: str) -> str:
    """Check edited content for syntax errors. Returns empty string if OK."""
    if not title or not content:
        return ""
    ext = Path(title).suffix.lower() if "." in title else ""
    if ext == ".py":
        try:
            compile(content, title, "exec")
            return ""
        except SyntaxError as e:
            return f"⚠ SyntaxError in {title}: {e}"
    return ""


def _do_edit_document_sync(content: str, doc_id: str | None = None, owner: str | None = None) -> dict:
    import uuid
    from datetime import datetime

    from core.database_models import Document, DocumentVersion, SessionLocal

    # Detect unified diff format (--- a/file +++ b/file)
    stripped = content.strip()
    if stripped.startswith("--- "):
        edits = parse_edit_blocks(content)
        target = doc_id or _active_document_id.get()
        if not target:
            return {"error": "No active document to apply diff to"}
        db = SessionLocal()
        try:
            doc = _get_owned_document(db, Document, target, owner)
            if not doc:
                return {"error": f"Document {target} not found"}
            new_text, err = _apply_unified_diff(doc.current_content, stripped)
            if new_text is None:
                return {"error": f"Unified diff apply failed: {err}"}
            ver_id = str(uuid.uuid4())
            ver = DocumentVersion(
                id=ver_id, document_id=target,
                version_number=doc.version_count + 1,
                content=doc.current_content,
                summary=f"Diff applied by {_active_model.get() or 'AI'}", source="ai",
            )
            doc.current_content = new_text
            doc.version_count += 1
            doc.updated_at = datetime.utcnow()
            db.add(ver)
            db.commit()
            verify_note = _verify_document_content(doc.title, new_text)
            details = [{"status": "ok", "match": "diff"}]
            if verify_note:
                details.append({"status": "verify", "note": verify_note})
            return {
                "action": "edit", "doc_id": target, "title": doc.title,
                "version": doc.version_count, "size": len(new_text),
                "applied": 1, "failed": 0,
                "details": details,
            }
        except Exception as e:
            db.rollback()
            return {"error": f"Failed to apply diff: {e}"}
        finally:
            db.close()

    edits = parse_edit_blocks(content)
    if not edits:
        return {"error": "No valid <<<FIND>>>...<<<REPLACE>>>...<<<END>>> blocks found in edit_document content"}

    # Group edits by doc_id (use active document as default)
    from collections import defaultdict
    by_doc: dict[str, list[dict]] = defaultdict(list)
    for ed in edits:
        target = ed.get("doc_id", "").strip() or doc_id or _active_document_id.get()
        if not target:
            return {"error": "No active document and no doc_id specified in edits. Use action='list' to find one."}
        by_doc[target].append(ed)

    db = SessionLocal()
    try:
        all_details = []
        total_applied = 0
        total_failed = 0
        title = ""

        # Process all docs in a single transaction
        for target_id, doc_edits in by_doc.items():
            doc = _get_owned_document(db, Document, target_id, owner)
            if not doc:
                for ed in doc_edits:
                    preview = ed.get("find_text", "")[:80].replace("\n", "\\n")
                    all_details.append({"status": "not_found", "find_preview": preview, "match": None, "doc_id": target_id})
                    total_failed += 1
                continue

            if not title:
                title = doc.title

            current = _normalize_text(doc.current_content)
            doc_new_content = current
            doc_details = []

            for ed in doc_edits:
                new_text, detail = _apply_edit_to_text(doc_new_content, ed)
                if new_text is None:
                    detail["doc_id"] = target_id
                    doc_details.append(detail)
                    total_failed += 1
                else:
                    doc_new_content = new_text
                    detail["doc_id"] = target_id
                    doc_details.append(detail)
                    total_applied += 1

            if any(d["status"] == "ok" for d in doc_details):
                ver_id = str(uuid.uuid4())
                ver = DocumentVersion(
                    id=ver_id,
                    document_id=target_id,
                    version_number=doc.version_count + 1,
                    content=doc.current_content,
                    summary=f"Edited by {_active_model.get() or 'AI'}",
                    source="ai",
                )
                doc.current_content = doc_new_content
                doc.version_count = doc.version_count + 1
                doc.updated_at = datetime.utcnow()
                db.add(ver)

            all_details.extend(doc_details)

        if total_applied == 0:
            db.rollback()
            return {"error": "No edits matched any document content", "details": all_details}

        db.commit()

        # Verify edited content (compile Python files, check for syntax errors)
        verify_notes = []
        for target_id, doc_edits in by_doc.items():
            if not any(d["status"] == "ok" for d in all_details if d.get("doc_id") == target_id):
                continue
            doc = _get_owned_document(db, Document, target_id, owner)
            if doc:
                note = _verify_document_content(doc.title, doc.current_content)
                if note:
                    verify_notes.append(note)
                    all_details.append({"status": "verify", "note": note, "doc_id": target_id})

        for _t_id in by_doc:
            try:
                from core.event_bus import fire_event
                fire_event("document_edited", owner)
            except Exception as e:
                logger.warning("[core.tools.document_tools] apply_unified_diff failed: %s", e)

        return {
            "action": "edit",
            "doc_id": doc_id or _active_document_id.get() or list(by_doc.keys())[0],
            "title": title,
            "version": 0,
            "size": 0,
            "applied": total_applied,
            "failed": total_failed,
            "details": all_details,
        }
    except Exception as e:
        db.rollback()
        return {"error": f"Failed to edit document: {e}"}
    finally:
        db.close()


async def do_edit_document(content: str, doc_id: str | None = None, owner: str | None = None) -> dict:
    return await asyncio.to_thread(_do_edit_document_sync, content, doc_id, owner)


# Manage documents (list, read, delete, tidy)

async def do_manage_documents(content: str, owner: str | None = None) -> dict:
    from datetime import datetime

    from core.database_models import Document, SessionLocal

    try:
        args = _parse_tool_args(content)
    except ValueError:
        return {"error": "Invalid JSON arguments", "exit_code": 1}

    action = args.get("action", "list")
    db = SessionLocal()

    def _rel(ts):
        if not ts:
            return 'never'
        try:
            now = datetime.now(UTC) if ts.tzinfo is not None else datetime.utcnow()
            diff = (now - ts).total_seconds()
        except Exception as _e:
            logger.debug("_format_last_seen ts diff failed: %s", _e)
            return 'unknown'
        if diff < 60: return 'just now'
        if diff < 3600: return f'{int(diff / 60)}m ago'
        if diff < 86400: return f'{int(diff / 3600)}h ago'
        if diff < 86400 * 7: return f'{int(diff / 86400)}d ago'
        return ts.strftime('%Y-%m-%d')

    try:
        if action == "list":
            q = db.query(Document).filter(Document.is_active == True)
            q = _owned_document_query(q, Document, owner)
            if args.get("search"):
                q = q.filter(Document.title.ilike(f"%{args['search']}%"))
            if args.get("language"):
                q = q.filter(Document.language == args["language"])
            docs = q.order_by(Document.updated_at.desc()).limit(args.get("limit", 50)).all()
            if not docs:
                msg = "No documents found" + (f" matching '{args['search']}'" if args.get("search") else "") + "."
                return {"response": msg, "documents": [], "exit_code": 0}
            lines = []
            items = []
            for i, d in enumerate(docs):
                size = len(d.current_content or "")
                lang = d.language or "text"
                ts = getattr(d, 'updated_at', None) or getattr(d, 'created_at', None)
                marker = " ← most recent" if i == 0 else ""
                lines.append(
                    f"- [{d.title}](#document-{d.id}) — {lang}, {size} chars, updated {_rel(ts)}{marker}"
                )
                items.append({"id": d.id, "title": d.title, "language": lang, "size": size})
            header = f"Found {len(docs)} document(s), sorted most-recent first. Click a title to open:"
            return {
                "response": header + "\n" + "\n".join(lines),
                "documents": items,
                "exit_code": 0,
            }

        elif action in ("read", "view", "open", "get"):
            doc_id = args.get("document_id") or args.get("id") or args.get("uid")
            if not doc_id:
                return {"error": "Need document_id (use action=list to find one)", "exit_code": 1}
            doc = _get_owned_document(db, Document, doc_id, owner, active_only=True)
            if not doc:
                return {"error": f"Document '{doc_id}' not found", "exit_code": 1}
            body = doc.current_content or ""
            preview_limit = int(args.get("limit", MAX_READ_CHARS))
            truncated = len(body) > preview_limit
            preview = body[:preview_limit] + (f"\n... (truncated, {len(body)} chars total)" if truncated else "")
            anchor = f"[{doc.title}](#document-{doc.id})"
            return {
                "response": f"{anchor} — click to open in editor.\n\n```{doc.language or ''}\n{preview}\n```",
                "document": {
                    "id": doc.id,
                    "title": doc.title,
                    "language": doc.language,
                    "size": len(body),
                    "content": preview,
                    "truncated": truncated,
                },
                "exit_code": 0,
            }

        elif action == "delete":
            doc_id = args.get("document_id") or args.get("id") or args.get("uid") or _active_document_id.get()
            doc = None
            if doc_id:
                doc = _get_owned_document(db, Document, doc_id, owner)
            if not doc:
                doc = _most_recent_owned_document(db, Document, owner, active_only=True)
            if not doc:
                return {"error": "No document to delete", "exit_code": 1}
            title = doc.title
            doc.is_active = False
            db.commit()
            if _active_document_id.get() == doc.id:
                set_active_document(None)
            return {"response": f"Deleted document '{title}'", "exit_code": 0}

        elif action == "tidy":
            from core.document_actions import run_document_tidy
            result = await run_document_tidy(owner or "")
            return {"response": result, "exit_code": 0}

        else:
            return {"error": f"Unknown action: {action}", "exit_code": 1}
    except Exception as e:
        logger.error(f"manage_documents error: {e}")
        return {"error": str(e), "exit_code": 1}
    finally:
        db.close()
