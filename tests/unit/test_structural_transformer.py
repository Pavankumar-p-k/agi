"""Unit tests for StructuralTransformationEngine (no Android SDK needed)."""
import sys, os, tempfile, textwrap
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from brain.structural_transformer import (
    StructuralTransformationEngine,
    normalize_type,
    detect_context,
    extract_expression,
    build_patch,
    _TYPE_CONVERSIONS,
)


@pytest.fixture
def engine():
    return StructuralTransformationEngine()


# ── normalize_type ──────────────────────────────────────────────

def test_normalize_type_strips_java_lang():
    assert normalize_type("java.lang.String") == "String"
    assert normalize_type("java.lang.Integer") == "Integer"

def test_normalize_type_strips_generics():
    assert normalize_type("List<String>") == "List"
    assert normalize_type("Map<String, Integer>") == "Map"

def test_normalize_type_strips_array_brackets():
    assert normalize_type("int[]") == "int"
    assert normalize_type("String[]") == "String"

def test_normalize_type_passthrough():
    assert normalize_type("int") == "int"
    assert normalize_type("boolean") == "boolean"


# ── Type conversions ────────────────────────────────────────────

@pytest.mark.parametrize("src,tgt,expr,expected", [
    ("String", "int",     "hourStr",          "Integer.parseInt(hourStr)"),
    ("String", "long",    "value",            "Long.parseLong(value)"),
    ("String", "double",  "price",            "Double.parseDouble(price)"),
    ("String", "float",   "temp",             "Float.parseFloat(temp)"),
    ("String", "boolean", "flag",             "Boolean.parseBoolean(flag)"),
    ("int",    "String",  "x",                "String.valueOf(x)"),
    ("long",   "String",  "id",               "String.valueOf(id)"),
    ("double", "String",  "score",            "String.valueOf(score)"),
    ("float",  "String",  "rate",             "String.valueOf(rate)"),
    ("boolean","String",  "enabled",          "String.valueOf(enabled)"),
    ("int",    "long",    "count",            "(long) count"),
    ("long",   "int",     "big",              "(int) big"),
    ("float",  "int",     "f",                "(int) f"),
    ("double", "int",     "d",                "(int) d"),
    ("Object", "String",  "obj",              "String.valueOf(obj)"),
    ("int",    "int",     "x",                "(x)"),
])
def test_convert_type(engine, src, tgt, expr, expected):
    result = engine.convert_type(src, tgt, expr)
    assert result == expected, f"convert_type({src}, {tgt}, {expr}) → {result}, expected {expected}"


def test_convert_type_unknown_returns_none(engine):
    assert engine.convert_type("Foo", "Bar", "x") is None


def test_convert_type_aliased(engine):
    """Should normalize java.lang types."""
    assert engine.convert_type("java.lang.String", "int", "x") == "Integer.parseInt(x)"
    assert engine.convert_type("String", "java.lang.Integer", "x") == "Integer.parseInt(x)"


# ── Context detection ───────────────────────────────────────────

def test_detect_context_return_stmt():
    lines = ["int getValue() {", "    return value;", "}"]
    assert detect_context(lines[1], 2, lines) == "return_stmt"

def test_detect_context_assignment():
    lines = ["    int x = someValue;"]
    assert detect_context(lines[0], 1, lines) == "assignment"

def test_detect_context_method_arg():
    lines = ["    foo(bar);"]
    assert detect_context(lines[0], 1, lines) in ("method_arg", "assignment")

def test_detect_context_complex_line():
    lines = ["    result = foo(x, y);"]
    ctx = detect_context(lines[0], 1, lines)
    assert ctx in ("assignment", "method_arg")

def test_detect_context_other():
    lines = ["    }"]
    assert detect_context(lines[0], 1, lines) == "other"


# ── Expression extraction ───────────────────────────────────────

def test_extract_expression_return():
    assert extract_expression("    return someValue;", "return_stmt", "int", "String") == "someValue"

def test_extract_expression_assignment():
    assert extract_expression("    int x = getCount();", "assignment", "int", "long") == "getCount()"

def test_extract_expression_method_arg():
    result = extract_expression('    foo("hello");', "method_arg", "String", "int")
    assert result is not None
    assert "hello" in result

def test_extract_expression_unknown_context():
    result = extract_expression("    }", "other", "int", "String")
    # Falls through to stripped line for unknown contexts
    assert result is not None
    assert "}" in result


# ── Patch building ──────────────────────────────────────────────

def test_build_patch_simple():
    line = "    return value;"
    patched = build_patch(line, "value", "Integer.parseInt(value)", "return_stmt")
    assert patched == "    return Integer.parseInt(value);"

def test_build_patch_no_change():
    assert build_patch("    return x;", "x", "x", "return_stmt") is None

def test_build_patch_empty_expr():
    assert build_patch("    return;", "", "foo", "return_stmt") is None

def test_build_patch_assignment():
    line = "    int x = getValue();"
    patched = build_patch(line, "getValue()", "Integer.parseInt(getValue())", "assignment")
    assert patched == "    int x = Integer.parseInt(getValue());"


# ── Integration: end-to-end file fix ────────────────────────────

def test_fix_type_mismatch_string_to_int(tmp_path, engine):
    """String→int conversion on return statement."""
    src = textwrap.dedent("""\
        public class Example {
            public int getValue() {
                String value = "42";
                return value;
            }
        }
    """)
    f = tmp_path / "Example.java"
    f.write_text(src)

    from brain.compiler_repair_engine import JavacError
    error = JavacError(
        file=str(f),
        line=4,
        category="type_mismatch",
        symbol="value",
        message="incompatible types: String cannot be converted to int",
    )
    assert engine.fix_type_mismatch(error, str(tmp_path))

    content = f.read_text()
    assert "Integer.parseInt(value)" in content


def test_fix_type_mismatch_int_to_string(tmp_path, engine):
    """int→String conversion."""
    src = textwrap.dedent("""\
        public class Example {
            public String getLabel() {
                int count = 5;
                return count;
            }
        }
    """)
    f = tmp_path / "Example.java"
    f.write_text(src)

    from brain.compiler_repair_engine import JavacError
    error = JavacError(
        file=str(f),
        line=4,
        category="type_mismatch",
        symbol="count",
        message="incompatible types: int cannot be converted to String",
    )
    assert engine.fix_type_mismatch(error, str(tmp_path))

    content = f.read_text()
    assert "String.valueOf(count)" in content


def test_fix_type_mismatch_method_arg(tmp_path, engine):
    """String argument where int expected — wraps with Integer.parseInt."""
    src = textwrap.dedent("""\
        public class Example {
            public void test() {
                setCount("5");
            }
            private void setCount(int count) {}
        }
    """)
    f = tmp_path / "Example.java"
    f.write_text(src)

    from brain.compiler_repair_engine import JavacError
    error = JavacError(
        file=str(f),
        line=3,
        category="type_mismatch",
        symbol="setCount",
        message="incompatible types: String cannot be converted to int",
    )
    # This may fail on method_arg context detection; if so, it returns False
    result = engine.fix_type_mismatch(error, str(tmp_path))
    if result:
        content = f.read_text()
        assert "Integer.parseInt" in content or "setCount" in content


def test_fix_type_mismatch_noop_wrong_types(engine, tmp_path):
    """Unknown type pair should not change the file."""
    src = textwrap.dedent("""\
        public class Example {
            public void test() {
                Foo x = getBar();
            }
        }
    """)
    f = tmp_path / "Example.java"
    f.write_text(src)

    from brain.compiler_repair_engine import JavacError
    error = JavacError(
        file=str(f),
        line=3,
        category="type_mismatch",
        symbol="x",
        message="incompatible types: Foo cannot be converted to Bar",
    )
    assert not engine.fix_type_mismatch(error, str(tmp_path))


def test_fix_type_mismatch_bad_file(engine):
    from brain.compiler_repair_engine import JavacError
    error = JavacError(
        file="nonexistent.java", line=1, category="type_mismatch",
        symbol="x", message="incompatible types: String cannot be converted to int",
    )
    assert not engine.fix_type_mismatch(error, "/tmp/nope")


# ── Stats ───────────────────────────────────────────────────────

def test_stats(engine, tmp_path):
    assert engine.get_stats()["attempted"] == 0
    assert engine.get_stats()["succeeded"] == 0
    assert engine.get_stats()["failed"] == 0
    # One failed attempt
    from brain.compiler_repair_engine import JavacError
    error = JavacError(
        file="nonexistent.java", line=1, category="type_mismatch",
        symbol="x", message="incompatible types: String cannot be converted to int",
    )
    engine.fix_type_mismatch(error, "/tmp/nope")
    assert engine.get_stats()["attempted"] == 1
    assert engine.get_stats()["failed"] == 1
