"""Kernel tests: store, events, audit chain, registry, policy, tasks."""

from __future__ import annotations

import json

import pytest

from mj.core import audit, events, policy, registry, tasks
from mj.core.registry import Manifest, RegistryError
from mj.core.store import Store


@pytest.fixture()
def store(tmp_path):
    s = Store.open(tmp_path)
    yield s
    s.close()


def manifest(**overrides):
    defaults = dict(
        id="os.facts",
        type="os",
        version="1.0.0",
        source="builtin",
        risk_class="R0",
        description="Read machine facts.",
    )
    defaults.update(overrides)
    return Manifest(**defaults)


# -- store ---------------------------------------------------------------


def test_store_reopen_persists_data(tmp_path):
    s = Store.open(tmp_path)
    s.set_meta("k", "v")
    s.close()
    s2 = Store.open(tmp_path)
    assert s2.get_meta("k") == "v"
    # migrations are idempotent
    s2._migrate()
    s2.close()


def test_store_runs_in_wal_mode(store):
    mode = store.one("PRAGMA journal_mode")["journal_mode"]
    assert mode.lower() == "wal"


# -- events / state machine ----------------------------------------------


def test_task_transitions_record_events(store):
    t = tasks.create(store, "check disk", "local-terminal")
    tasks.transition(store, t["id"], "planned", {"steps": 1})
    tasks.transition(store, t["id"], "policy_checked")
    tasks.transition(store, t["id"], "executing")
    evs = events.for_task(store, t["id"])
    kinds = [e["kind"] for e in evs]
    assert kinds == ["task.created", "task.transition", "task.transition", "task.transition"]
    assert events.for_task(store, t["id"])[0]["payload"]["goal"] == "check disk"


def test_invalid_transition_rejected(store):
    t = tasks.create(store, "g", "local-terminal")
    with pytest.raises(ValueError, match="invalid task transition"):
        tasks.transition(store, t["id"], "done")  # cannot skip to done from received


def test_concurrent_transition_detected(store):
    t = tasks.create(store, "g", "local-terminal")
    # a plan that believes the task is 'executing' while the row disagrees:
    # the optimistic UPDATE ... WHERE state='executing' changes nothing and the
    # mistimed transition is refused instead of double-applied
    with pytest.raises(ValueError, match="not in expected state"):
        events.record_transition(store, t["id"], "executing", "verifying")


# -- audit chain ----------------------------------------------------------


def test_audit_chain_verifies_and_detects_tampering(store):
    a1 = audit.append(store, "user", "task.create", {"id": "t1"})
    a2 = audit.append(store, "kernel", "policy.decision", {"action": "ask"})
    assert a2["seq"] > a1["seq"]
    ok, count, problem = audit.verify(store)
    assert ok and count == 2

    # tamper with a recorded payload -> chain verification must fail
    store.execute(
        "UPDATE audit_entries SET payload_json = ? WHERE seq = ?",
        (json.dumps({"id": "t1", "tampered": True}), a1["seq"]),
    )
    ok, count, problem = audit.verify(store)
    assert not ok and "hash mismatch" in problem


def test_audit_entries_are_ordered_with_link_hashes(store):
    audit.append(store, "a", "x", {})
    audit.append(store, "b", "y", {})
    audit.append(store, "c", "z", {})
    es = list(reversed(audit.entries(store, limit=10)))
    assert es[0]["prev_hash"] == audit.GENESIS_HASH
    assert es[1]["prev_hash"] == es[0]["entry_hash"]


# -- registry --------------------------------------------------------------


def test_register_and_get_roundtrip(store):
    m = manifest()
    registry.register(store, m, status="healthy")
    got = registry.get(store, "os.facts")
    assert got is not None
    m2, status = got
    assert m2.to_dict() == m.to_dict()
    assert status == "healthy"
    # idempotent re-registration does not error
    registry.register(store, m, status="healthy")


def test_invalid_manifests_rejected(store):
    with pytest.raises(RegistryError):
        registry.register(store, manifest(risk_class="R9"))
    with pytest.raises(RegistryError):
        registry.register(store, manifest(type="telepathy"))
    with pytest.raises(RegistryError):
        registry.register(store, manifest(id="bad id with spaces"))
    with pytest.raises(RegistryError):
        registry.register(store, manifest(version=""))


def test_sensitive_powers_require_risk_class_and_verifier(store):
    """Registration rule (docs/07 §2): any manifest declaring web/browser/
    shell powers must be R2+ and carry an independent verifier — enforced for
    every registration path, not just today's builtins."""
    # R0 web capability: rejected (would run without approval)
    with pytest.raises(RegistryError, match="sensitive power"):
        registry.validate_manifest(manifest(id="web.open", risk_class="R0"))
    # R2 shell capability without a verifier: rejected
    with pytest.raises(RegistryError, match="verifier"):
        registry.validate_manifest(
            manifest(id="shell.exec", risk_class="R2", has_verifier=False)
        )
    # browser-typed capability below R2: rejected even with a clean id
    with pytest.raises(RegistryError, match="sensitive power"):
        registry.validate_manifest(
            manifest(id="nav.tab", type="browser", risk_class="R1", has_verifier=True)
        )
    # scope-declared web power: rejected at R0
    with pytest.raises(RegistryError, match="sensitive power"):
        registry.validate_manifest(
            manifest(id="agent.fetch", risk_class="R0", requires_scopes=["web.fetch"])
        )
    # word-level matching: 'shellpaper' is not shell, 'web-worker' is web
    registry.validate_manifest(manifest(id="files.shellpaper", risk_class="R0"))
    with pytest.raises(RegistryError, match="sensitive power"):
        registry.validate_manifest(
            manifest(id="agent.web-worker", risk_class="R0", source="generated")
        )
    # a conforming browser capability (as BrowserOS would be) registers fine
    registry.register(
        store,
        manifest(
            id="browser.open",
            type="browser",
            risk_class="R2",
            has_verifier=True,
            description="open a URL in the registered browser worker",
            effects=["network"],
        ),
        status="healthy",
    )
    assert registry.get(store, "browser.open") is not None


def test_powers_and_effects_must_agree(store):
    """Effects rule (docs/09 §3): declaring a sensitive power requires the
    matching effect, the vocabulary is closed, and a sensitive effect can
    never sit below its risk floor — so a capability named 'helper' that
    shells out cannot register as a silent R0."""
    # shell power at R2 with a verifier, but no declared process effect
    with pytest.raises(RegistryError, match="required effect"):
        registry.validate_manifest(
            manifest(id="tool.shell", type="cli", risk_class="R2", has_verifier=True)
        )
    # the same capability, honestly declared: fine
    registry.validate_manifest(
        manifest(
            id="tool.shell",
            type="cli",
            risk_class="R2",
            has_verifier=True,
            effects=["process"],
        )
    )
    # closed vocabulary: invented effects are rejected
    with pytest.raises(RegistryError, match="unknown effect"):
        registry.validate_manifest(manifest(id="files.stats", effects=["mind.reading"]))
    # sensitive effect below its floor: network at R0 is impossible to register
    with pytest.raises(RegistryError, match="floor"):
        registry.validate_manifest(manifest(id="fetch.light", effects=["network"]))
    # secrets demand R3+; R2 secrets reader rejected, R3 accepted
    with pytest.raises(RegistryError, match="floor"):
        registry.validate_manifest(manifest(id="vault.read", risk_class="R2", effects=["secrets"]))
    registry.validate_manifest(manifest(id="vault.read", risk_class="R3", effects=["secrets"]))
    # non-sensitive effects have no floor: a plain R0 reader declaring
    # filesystem.read is exactly as before
    registry.validate_manifest(manifest(id="files.stats", effects=["filesystem.read"]))


def test_status_transitions_guarded(store):
    registry.register(store, manifest(), status="candidate")
    registry.set_status(store, "os.facts", "testing")
    registry.set_status(store, "os.facts", "healthy")
    with pytest.raises(RegistryError, match="illegal status transition"):
        registry.set_status(store, "os.facts", "candidate")  # healthy -> candidate illegal
    registry.set_status(store, "os.facts", "degraded")
    registry.set_status(store, "os.facts", "retired")
    with pytest.raises(RegistryError):
        registry.set_status(store, "os.facts", "healthy")  # retired is final


# -- policy gate -----------------------------------------------------------


def test_default_policy_decision_table(store):
    gate = policy.PolicyGate.load()
    assert gate.decide(store, "user", "R0", "local-terminal").action == "allow"
    assert gate.decide(store, "user", "R1", "local-terminal").action == "allow"
    assert gate.decide(store, "user", "R2", "local-terminal").action == "ask"
    assert gate.decide(store, "user", "R3", "local-terminal").action == "ask"
    assert gate.decide(store, "user", "R4", "local-terminal").action == "deny"
    # lower trust channels never get silent side effects
    assert gate.decide(store, "chat", "R1", "chat-connector").action == policy.DENY


def test_allow_is_escalated_to_ask_for_r3_r4(store, tmp_path):
    # a standing 'allow' rule for R3 still must ask — the gate escalates it
    rules_file = tmp_path / "standing.json"
    rules_file.write_text(
        json.dumps(
            {
                "default_action": "deny",
                "rules": [{"risk_class": "R3", "trust_types": ["local-terminal"], "action": "allow"}],
            }
        ),
        encoding="utf-8",
    )
    gate = policy.PolicyGate(
        policy._load_rules_from_dict(json.loads(rules_file.read_text(encoding="utf-8")), str(rules_file))
    )
    d = gate.decide(store, "user", "R3", "local-terminal")
    assert d.action == "ask"
    assert "always asks" in d.reason


def test_unknown_trust_denies_by_default(store):
    gate = policy.PolicyGate.load()
    d = gate.decide(store, "x", "R2", "external")
    assert d.action == "deny"


def test_policy_decisions_are_audited(store):
    gate = policy.PolicyGate.load()
    gate.decide(store, "user", "R1", "local-terminal")
    ok, count, _ = audit.verify(store)
    assert ok and count >= 1
    kinds = [e["action"] for e in audit.entries(store)]
    assert "policy.decision" in kinds


# -- tasks report ----------------------------------------------------------


def test_set_report_and_get(store):
    t = tasks.create(store, "g", "local-terminal")
    tasks.set_report(store, t["id"], {"summary": "ok", "verified": 2, "unverified": 0})
    got = tasks.get(store, t["id"])
    assert got["report"]["summary"] == "ok"
    assert got["state"] == "received"
