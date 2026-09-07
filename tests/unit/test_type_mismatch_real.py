"""Real-world type mismatch test: the exact C_type_mismatch scenario."""
import sys, os, tempfile, textwrap
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from brain.compiler_repair_engine import CompilerRepairEngine, JavacError


def test_fix_string_hour_to_int_like_c_type_mismatch():
    """
    The C_type_mismatch repo failure:
        String hour param used as int (Calendar.set(int, int))
        Old fix: (int) hour — invalid cast String→int
        New fix: Integer.parseInt(hour)
    """
    src = textwrap.dedent("""\
        import java.util.Calendar;

        public class AlarmScheduler {
            public void scheduleAlarm(String hour, String minute) {
                Calendar cal = Calendar.getInstance();
                cal.set(Calendar.HOUR_OF_DAY, hour, Calendar.MINUTE, minute);
            }
        }
    """)
    # Lines: 1=import, 2=blank, 3=class, 4=method, 5=cal.getInstance, 6=cal.set
    # Error on line 6: cal.set(...) where hour is String but int expected
    with tempfile.TemporaryDirectory() as tmp:
        f = os.path.join(tmp, "AlarmScheduler.java")
        with open(f, "w") as fh:
            fh.write(src)

        engine = CompilerRepairEngine(tmp)
        error = JavacError(
            file="AlarmScheduler.java",
            line=6,
            category="type_mismatch",
            symbol="hour",
            message="incompatible types: String cannot be converted to int",
        )
        result = engine._fix_type_mismatch(error, tmp)
        assert result, "StructuralTransformationEngine should fix String→int"

        with open(f) as fh:
            content = fh.read()
        assert "Integer.parseInt(hour)" in content, (
            f"Expected Integer.parseInt(hour) in fixed file, got:\n{content}"
        )


def test_fix_string_minute_to_int():
    """Same repo: String minute → int parameter."""
    src = textwrap.dedent("""\
        import java.util.Calendar;

        public class AlarmScheduler {
            public void scheduleAlarm(String hour, String minute) {
                Calendar cal = Calendar.getInstance();
                cal.set(Calendar.HOUR_OF_DAY, 10, Calendar.MINUTE, minute);
            }
        }
    """)
    # Error on line 6: cal.set(...) where minute is String but int expected
    with tempfile.TemporaryDirectory() as tmp:
        f = os.path.join(tmp, "AlarmScheduler.java")
        with open(f, "w") as fh:
            fh.write(src)

        engine = CompilerRepairEngine(tmp)
        error = JavacError(
            file="AlarmScheduler.java",
            line=6,
            category="type_mismatch",
            symbol="minute",
            message="incompatible types: String cannot be converted to int",
        )
        result = engine._fix_type_mismatch(error, tmp)
        assert result, "StructuralTransformationEngine should fix String→int"

        with open(f) as fh:
            content = fh.read()
        assert "Integer.parseInt(minute)" in content, (
            f"Expected Integer.parseInt(minute) in fixed file, got:\n{content}"
        )


def test_fix_int_to_string_return():
    """int→String return type mismatch."""
    src = textwrap.dedent("""\
        public class Converter {
            public String getLabel() {
                int count = 42;
                return count;
            }
        }
    """)
    # Lines: 1=class, 2=method, 3=decl, 4=return, 5=}
    # Error on line 4: return count where count is int but String expected
    with tempfile.TemporaryDirectory() as tmp:
        f = os.path.join(tmp, "Converter.java")
        with open(f, "w") as fh:
            fh.write(src)

        engine = CompilerRepairEngine(tmp)
        error = JavacError(
            file="Converter.java",
            line=4,
            category="type_mismatch",
            symbol="count",
            message="incompatible types: int cannot be converted to String",
        )
        result = engine._fix_type_mismatch(error, tmp)
        assert result, "Should fix int→String return type"

        with open(f) as fh:
            content = fh.read()
        assert "String.valueOf(count)" in content, (
            f"Expected String.valueOf(count), got:\n{content}"
        )


def test_string_literal_arg_to_int():
    """setHour("10") where setHour expects int."""
    src = textwrap.dedent("""\
        public class Scheduler {
            public void setAlarm() {
                setHour("10");
            }
            private void setHour(int hour) {}
        }
    """)
    with tempfile.TemporaryDirectory() as tmp:
        f = os.path.join(tmp, "Scheduler.java")
        with open(f, "w") as fh:
            fh.write(src)

        engine = CompilerRepairEngine(tmp)
        error = JavacError(
            file="Scheduler.java",
            line=3,
            category="type_mismatch",
            symbol="setHour",
            message="incompatible types: String cannot be converted to int",
        )
        result = engine._fix_type_mismatch(error, tmp)
        assert result, "Should fix String literal → int"

        with open(f) as fh:
            content = fh.read()
        assert "Integer.parseInt(" in content, (
            f"Expected Integer.parseInt in fixed file, got:\n{content}"
        )
