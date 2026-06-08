"""Tests for edit tool internals: diff application, fuzzy matching, edit blocks."""

from __future__ import annotations

import pytest

from core.tools.document_tools import (
    _apply_unified_diff,
    _find_edit_location,
    _normalize_text,
    _apply_edit_to_text,
    parse_edit_blocks,
)


# ── Unified diff ───────────────────────────────────────────────────────


class TestApplyUnifiedDiff:
    def test_simple_replacement(self):
        original = "line1\nline2\nline3"
        diff = "--- a/file\n+++ b/file\n@@ -1,3 +1,3 @@\n line1\n-line2\n+new_line2\n line3\n"
        result, err = _apply_unified_diff(original, diff)
        assert err == ""
        assert result == "line1\nnew_line2\nline3"

    def test_add_lines(self):
        original = "a\nb"
        diff = "--- a/f\n+++ b/f\n@@ -1,2 +1,4 @@\n a\n b\n+new_line\n+new_line2\n"
        result, err = _apply_unified_diff(original, diff)
        assert err == ""
        assert result == "a\nb\nnew_line\nnew_line2"

    def test_remove_lines(self):
        original = "keep\nremove_me\nkeep2"
        diff = "--- a/f\n+++ b/f\n@@ -1,3 +1,2 @@\n keep\n-remove_me\n keep2\n"
        result, err = _apply_unified_diff(original, diff)
        assert err == ""
        assert result == "keep\nkeep2"

    def test_multiple_hunks(self):
        original = "a\nb\nc\nd\ne\nf"
        diff = (
            "--- a/f\n+++ b/f\n"
            "@@ -1,3 +1,3 @@\n a\n-b\n+new_b\n c\n"
            "@@ -4,3 +4,3 @@\n d\n-e\n+new_e\n f\n"
        )
        result, err = _apply_unified_diff(original, diff)
        assert err == ""
        assert result == "a\nnew_b\nc\nd\nnew_e\nf"

    def test_context_mismatch_rejected(self):
        original = "line1\nline2\nline3"
        diff = "--- a/f\n+++ b/f\n@@ -1,3 +1,3 @@\n line1\n-WRONG_CONTEXT\n+new_line2\n line3\n"
        result, err = _apply_unified_diff(original, diff)
        assert result is None
        assert "context mismatch" in err

    def test_bad_hunk_count_rejected(self):
        original = "a\nb"
        diff = "--- a/f\n+++ b/f\n@@ -1,2 +1,3 @@\n a\n-b\n-c\n+d\n"
        result, err = _apply_unified_diff(original, diff)
        assert result is None
        assert "header says" in err.lower() or "but found" in err.lower()

    def test_empty_diff(self):
        original = "content"
        diff = "--- a/f\n+++ b/f\n"
        result, err = _apply_unified_diff(original, diff)
        assert result is None
        assert "No valid hunks" in err

    def test_no_trailing_newline(self):
        original = "line1\nline2"
        diff = "--- a/f\n+++ b/f\n@@ -1,2 +1,2 @@\n line1\n-line2\n+new_line2\n"
        result, err = _apply_unified_diff(original, diff)
        assert err == ""
        assert result == "line1\nnew_line2"

    def test_empty_file(self):
        original = ""
        diff = "--- a/f\n+++ b/f\n@@ -0,0 +1,1 @@\n+new_first_line\n"
        result, err = _apply_unified_diff(original, diff)
        assert err == ""
        assert result == "new_first_line"

    def test_carriage_return_normalized(self):
        # diff includes \r\n but content becomes \n
        original = "line1\r\nline2"
        diff = "--- a/f\n+++ b/f\n@@ -1,2 +1,2 @@\n line1\n-line2\n+new_line2\n"
        result, err = _apply_unified_diff(original, diff)
        assert err == ""
        # carriage returns are not removed by the diff function itself
        assert "new_line2" in result

    def test_real_world_edit(self):
        original = """def hello():
    print("hello world")
    return True

def goodbye():
    print("goodbye")"""
        diff = """--- a/file
+++ b/file
@@ -1,5 +1,7 @@
 def hello():
-    print("hello world")
+    name = "world"
+    print(f"hello {name}")
     return True
 
+
 def goodbye():
"""
        result, err = _apply_unified_diff(original, diff)
        assert err == "", f"Unexpected error: {err}"
        assert "name = \"world\"" in result
        assert 'print(f"hello {name}")' in result
        assert 'print("hello world")' not in result
        assert result == (
            'def hello():\n'
            '    name = "world"\n'
            '    print(f"hello {name}")\n'
            '    return True\n'
            '\n'
            '\n'
            'def goodbye():\n'
            '    print("goodbye")'
        )


# ── Fuzzy matching ─────────────────────────────────────────────────────


class TestFindEditLocation:
    def test_exact_match(self):
        idx, match = _find_edit_location("hello world\nfoo bar", "world")
        assert match == "exact"
        assert idx == 6

    def test_trailing_whitespace(self):
        idx, match = _find_edit_location("hello world  \nfoo bar", "hello world\n")
        assert match is not None

    def test_collapsed_spaces(self):
        idx, match = _find_edit_location("hello   world", "hello world")
        assert match is not None

    def test_no_match(self):
        idx, match = _find_edit_location("abc\ndef", "xyz")
        assert idx is None

    def test_line_number_prefix(self):
        text = "\n".join(f"line{i}" for i in range(1, 50))
        idx, match = _find_edit_location(text, "L25: line25")
        assert match is not None, "Should match by line number"
        assert "line25" in text[idx:idx + 10]

    def test_lcs_fallback(self):
        text = "the quick brown fox jumps over the lazy dog"
        needle = "the quick brwn fox jumps"
        idx, match = _find_edit_location(text, needle)
        assert match is not None, "LCS should handle typos"
        assert "fuzzy" in match

    def test_empty_needle(self):
        idx, match = _find_edit_location("some text", "")
        assert idx is not None

    def test_unicode_preserved(self):
        text = "café\nrésumé\n"
        idx, match = _find_edit_location(text, "café")
        assert match == "exact"
        assert text[idx:idx + 4] == "café"


# ── Edit application ───────────────────────────────────────────────────


class TestApplyEditToText:
    def test_exact_replacement(self):
        current = "before\nOLD\nafter"
        ed = {"find_text": "OLD", "replace": "NEW", "find": "OLD"}
        new, detail = _apply_edit_to_text(current, ed)
        assert detail["status"] == "ok"
        assert new == "before\nNEW\nafter"

    def test_not_found(self):
        current = "hello"
        ed = {"find_text": "nonexistent", "replace": "x", "find": "nonexistent"}
        new, detail = _apply_edit_to_text(current, ed)
        assert detail["status"] == "not_found"
        assert new is None

    def test_normalized_match(self):
        current = "keep\nhello  \nkeep2"
        ed = {"find_text": "hello\n", "replace": "world\n", "find": "hello\n"}
        new, detail = _apply_edit_to_text(current, ed)
        assert detail["status"] == "ok"
        assert "world" in new
        assert "keep" in new


# ── Edit block parsing ─────────────────────────────────────────────────


class TestParseEditBlocks:
    def test_single_block(self):
        text = "<<<FIND>>>\nold\n<<<REPLACE>>>\nnew\n<<<END>>>"
        result = parse_edit_blocks(text)
        assert len(result) == 1
        assert result[0]["find_text"] == "old"
        assert result[0]["replace"] == "new"

    def test_multiple_blocks(self):
        text = (
            "<<<FIND>>>\nfirst_old\n<<<REPLACE>>>\nfirst_new\n<<<END>>>\n"
            "<<<FIND>>>\nsecond_old\n<<<REPLACE>>>\nsecond_new\n<<<END>>>"
        )
        result = parse_edit_blocks(text)
        assert len(result) == 2
        assert result[0]["find_text"] == "first_old"
        assert result[1]["find_text"] == "second_old"

    def test_block_with_doc_id(self):
        text = "<<<FIND>>>\nold\n<<<REPLACE>>>\nnew\n<<<DOC_ID>>>\ndoc123\n<<<END>>>"
        result = parse_edit_blocks(text)
        assert len(result) == 1
        assert result[0]["doc_id"] == "doc123"

    def test_no_blocks_returns_empty(self):
        result = parse_edit_blocks("just regular text")
        assert result == []


# ── Edge cases ─────────────────────────────────────────────────────────


class TestEditEdgeCases:
    def test_diff_on_empty_string(self):
        result, err = _apply_unified_diff("", "")
        assert result is None

    def test_noop_diff(self):
        text = "hello\nworld"
        diff = "--- a/f\n+++ b/f\n@@ -1,2 +1,2 @@\n hello\n world\n"
        result, err = _apply_unified_diff(text, diff)
        assert err == ""
        assert result == text

    def test_find_location_with_unicode_whitespace(self):
        text = "a\u00a0b"
        idx, match = _find_edit_location(text, "a b")
        assert match is not None

    def test_very_long_find_text_match(self):
        text = "prefix " + "x" * 500 + " suffix"
        needle = "x" * 500
        idx, match = _find_edit_location(text, needle)
        assert match == "exact"

    def test_all_lines_removed(self):
        text = "only_line"
        diff = "--- a/f\n+++ b/f\n@@ -1,1 +0,0 @@\n-only_line\n"
        result, err = _apply_unified_diff(text, diff)
        assert err == ""
        assert result == ""

    def test_malformed_diff(self):
        result, err = _apply_unified_diff("abc", "not a diff at all")
        assert result is None
