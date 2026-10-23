"""Mutation kill-test harness — CI gate for adversarial-suite strength.

Each entry disables one defense in the source on purpose, runs the matching
adversarial tests, and requires them to FAIL (a surviving mutation means the
test tests nothing). The file is then restored from a byte-exact backup and
the same tests must pass again. Exits nonzero if any defense survives.

Run:  python tools/mutation_check.py            (or from CI, same command)
No third-party deps beyond pytest, which the suite already needs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MUTATION_MARKER = "MUTATION-CHECK-DISABLED"


@dataclass(frozen=True)
class Mutation:
    name: str
    file: str
    old: str
    new: str
    tests: list[str] = field(default_factory=list)


MUTATIONS: list[Mutation] = [
    Mutation(
        name="approval-payload binding (hash)",
        file="src/mj/executor/runner.py",
        old='def _payload_hash(step: planner.Step) -> str:\n'
            '    return hashlib.sha256(canonical_json(step.to_dict()).encode("utf-8")).hexdigest()',
        new='def _payload_hash(step: planner.Step) -> str:\n'
            f'    return "0" * 64  # {MUTATION_MARKER}',
        tests=[
            "tests/adversarial/test_adversarial.py::"
            "test_granted_approval_does_not_authorize_a_changed_payload"
        ],
    ),
    Mutation(
        name="verifier independence (trust worker output)",
        file="src/mj/executor/runner.py",
        old='            output = _run_step(store, step.capability_id, exec_inputs, timeout_s)\n'
            '            output = broker.redact(output, known)\n'
            '            evidence = impl.verify(store, dict(step.inputs), output)\n'
            '            verified = bool(evidence.get("verified"))',
        new='            output = _run_step(store, step.capability_id, exec_inputs, timeout_s)\n'
            '            output = broker.redact(output, known)\n'
            f'            evidence = {{"verified": True, "detail": "{MUTATION_MARKER}"}}\n'
            '            verified = True',
        tests=[
            "tests/adversarial/test_adversarial.py::test_worker_claims_success_verifier_refutes",
            "tests/adversarial/test_adversarial.py::test_organize_reports_moves_that_never_happened",
        ],
    ),
    Mutation(
        name="secret redaction (worker output and errors)",
        file="src/mj/executor/broker.py",
        old='    if not secrets:\n'
            '        return value\n'
            '    return _redact_walk(value, secrets)',
        new='    if not secrets:\n'
            '        return value\n'
            f'    return value  # {MUTATION_MARKER}',
        tests=[
            "tests/adversarial/test_canary_leaks.py::test_canary_in_worker_output_is_redacted",
            "tests/adversarial/test_canary_leaks.py::test_canary_in_worker_exception_is_redacted",
            "tests/adversarial/test_canary_leaks.py::"
            "test_canary_printed_or_left_in_stderr_survives_nowhere",
        ],
    ),
    Mutation(
        name="credential scope enforcement (requires_scopes)",
        file="src/mj/executor/broker.py",
        old='        if n not in allowed_set:\n'
            '            raise BrokerError(\n'
            '                f"secret {n!r} is not in this capability\'s requires_scopes"\n'
            '            )',
        new=f'        if False:  # {MUTATION_MARKER}\n'
            '            raise BrokerError(\n'
            '                f"secret {n!r} is not in this capability\'s requires_scopes"\n'
            '            )',
        tests=["tests/adversarial/test_canary_leaks.py::test_out_of_scope_secret_is_refused"],
    ),
    Mutation(
        name="escape check (path traversal)",
        file="src/mj/executor/capabilities.py",
        old='    resolved = (base / relative).resolve()\n'
            '    try:\n'
            '        resolved.relative_to(base.resolve())\n'
            '    except ValueError:\n'
            '        return True\n'
            '    return False',
        new=f'    return False  # {MUTATION_MARKER}',
        tests=[
            "tests/adversarial/test_adversarial.py::"
            "test_lying_worker_cannot_move_files_out_of_the_sandbox",
            "tests/adversarial/test_adversarial.py::"
            "test_undo_refuses_to_pull_files_in_from_outside_the_sandbox",
        ],
    ),
    Mutation(
        name="step-result write-once (late write loses)",
        file="src/mj/executor/runner.py",
        old='        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(idempotency_key) DO NOTHING",',
        new='        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(idempotency_key) DO UPDATE SET "'
            '        "output_json=excluded.output_json, verified=excluded.verified, "'
            '        "evidence_json=excluded.evidence_json /* MUTATION-CHECK-DISABLED */",',
        tests=[
            "tests/unit/test_limits.py::test_late_or_duplicate_result_write_is_discarded_not_overwritten"
        ],
    ),
    Mutation(
        name="power -> effect cross-check",
        file="src/mj/core/registry.py",
        old='        for power in sorted(powers):\n'
            '            needed = POWER_EFFECTS.get(power)\n'
            '            if needed and needed not in m.effects:',
        new='        for power in sorted(powers):\n'
            f'            needed = POWER_EFFECTS.get(power) if not "{MUTATION_MARKER}" else None\n'
            '            if needed and needed not in m.effects:',
        tests=[
            "tests/unit/test_kernel.py::test_powers_and_effects_must_agree"
        ],
    ),
    Mutation(
        name="registry sensitive-power rule",
        file="src/mj/core/registry.py",
        old='    powers = declared_powers(m)\n'
            '    if powers:',
        new=f'    powers = declared_powers(m) if not "{MUTATION_MARKER}" else set()\n'
            '    if powers:',
        tests=[
            "tests/unit/test_kernel.py::test_sensitive_powers_require_risk_class_and_verifier",
            "tests/adversarial/test_adversarial.py::"
            "test_no_registered_capability_can_open_a_url_or_run_a_shell",
        ],
    ),
]


def run_pytest(tests: list[str]) -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *tests],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode


def apply_mutation(m: Mutation) -> Path:
    src = ROOT / m.file
    text = src.read_text(encoding="utf-8")
    if m.old not in text:
        raise RuntimeError(
            f"mutation {m.name!r}: anchor not found in {m.file} — the source "
            "changed shape; update MUTATIONS to match the current defense"
        )
    # close the mkstemp fd immediately — on Windows an open handle blocks the
    # later restore/unlink (WinError 32)
    fd, backup_name = tempfile.mkstemp(suffix=".bak", prefix="mjmut_")
    os.close(fd)
    backup = Path(backup_name)
    shutil.copy2(src, backup)
    src.write_text(text.replace(m.old, m.new, 1), encoding="utf-8")
    return backup


def restore(m: Mutation, backup: Path) -> None:
    src = ROOT / m.file
    shutil.copy2(backup, src)
    backup.unlink(missing_ok=True)
    if MUTATION_MARKER in src.read_text(encoding="utf-8"):
        raise RuntimeError(f"restore failed: marker still present in {m.file}")


def main() -> int:
    survivors: list[str] = []
    for m in MUTATIONS:
        print(f"[mutation] {m.name} ({m.file})")
        baseline = run_pytest(m.tests)
        if baseline != 0:
            print(f"  ERROR: baseline tests FAILED before mutating ({baseline}); fix the suite first")
            return 2
        backup = apply_mutation(m)
        try:
            mutated = run_pytest(m.tests)
            if mutated == 0:
                survivors.append(m.name)
                print("  SURVIVED: tests stayed green with the defense disabled")
            else:
                print(f"  killed: tests went red with the defense disabled (exit {mutated})")
        finally:
            restore(m, backup)
        restored = run_pytest(m.tests)
        if restored != 0:
            print(f"  ERROR: tests failed after restore (exit {restored}); check restore integrity")
            return 2
        print("  restored: green again")
    print()
    if survivors:
        print(f"FAIL: {len(survivors)} defense(s) survived mutation: {survivors}")
        return 1
    print(f"OK: all {len(MUTATIONS)} defenses are load-bearing; every mutation was killed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
