"""Broker tests: vetted AEAD, key sources, scope enforcement, redaction."""

from __future__ import annotations

import base64
import json

import pytest

from mj.core.store import Store
from mj.executor import broker


@pytest.fixture()
def store(tmp_path):
    s = Store.open(tmp_path)
    yield s
    s.close()


def _record_path(store: Store, name: str):
    return store.path.parent / "broker" / f"{name}.json"


# -- encryption ---------------------------------------------------------------


def test_roundtrip_metadata_and_no_plaintext_on_disk(store):
    broker.set_secret(store, "token", "s3cr3t-value-1234")
    assert broker.get_secret(store, "token") == "s3cr3t-value-1234"

    meta = broker.secret_meta(store, "token")
    assert meta["key"] == "token"
    assert meta["created"] is not None
    assert meta["last_used"] is None
    assert "s3cr3t-value-1234" not in json.dumps(meta)

    rec = json.loads(_record_path(store, "token").read_text(encoding="utf-8"))
    assert rec["alg"] == "aes-256-gcm"
    assert "s3cr3t-value-1234" not in json.dumps(rec)


def test_record_is_bound_to_its_name(store):
    """The name is AEAD associated data: swapping records must not decrypt."""
    broker.set_secret(store, "alpha", "value-alpha")
    broker.set_secret(store, "beta", "value-beta")
    _record_path(store, "beta").write_text(
        _record_path(store, "alpha").read_text(encoding="utf-8"), encoding="utf-8"
    )
    with pytest.raises(broker.BrokerError) as excinfo:
        broker.get_secret(store, "beta")
    assert "authentication" in str(excinfo.value)


def test_tampered_ciphertext_is_refused(store):
    broker.set_secret(store, "token", "value-tamper")
    path = _record_path(store, "token")
    rec = json.loads(path.read_text(encoding="utf-8"))
    ct = bytearray(base64.b64decode(rec["ct"], validate=True))
    ct[0] ^= 0x01
    rec["ct"] = base64.b64encode(bytes(ct)).decode("ascii")
    path.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(broker.BrokerError):
        broker.get_secret(store, "token")


def test_old_hand_rolled_records_are_refused_with_advice(store):
    path = _record_path(store, "legacy")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"v": 1, "ct": "AA==", "nonce": "AA=="}), encoding="utf-8")
    with pytest.raises(broker.BrokerError) as excinfo:
        broker.get_secret(store, "legacy")
    assert "re-set" in str(excinfo.value)


def test_secret_shorter_than_redaction_can_scrub_is_refused(store):
    with pytest.raises(broker.BrokerError) as excinfo:
        broker.set_secret(store, "tiny", "abc")
    assert "short" in str(excinfo.value)


# -- master key sources -------------------------------------------------------


def test_env_key_overrides_and_wrong_key_fails(store, monkeypatch):
    monkeypatch.setenv("MJ_BROKER_KEY", "11" * 32)
    broker.set_secret(store, "token", "value-env-key")
    assert broker.get_secret(store, "token") == "value-env-key"

    monkeypatch.setenv("MJ_BROKER_KEY", "22" * 32)
    with pytest.raises(broker.BrokerError):
        broker.get_secret(store, "token")


def test_os_keyring_is_preferred_and_no_key_file_is_written(store, monkeypatch):
    vault: dict[str, str] = {}
    monkeypatch.delenv("MJ_BROKER_KEY", raising=False)
    monkeypatch.setattr(broker, "_keyring_read", lambda: vault.get("key"))

    def _write(hex_key: str) -> bool:
        vault["key"] = hex_key
        return True

    monkeypatch.setattr(broker, "_keyring_write", _write)

    broker.set_secret(store, "token", "value-keyring")
    assert len(bytes.fromhex(vault["key"])) == 32
    assert not (store.path.parent / "broker" / ".master.key").exists()
    assert broker.get_secret(store, "token") == "value-keyring"


def test_key_file_fallback_when_keyring_unavailable(store, monkeypatch):
    monkeypatch.delenv("MJ_BROKER_KEY", raising=False)
    monkeypatch.setattr(broker, "_keyring_read", lambda: None)
    monkeypatch.setattr(broker, "_keyring_write", lambda hex_key: False)

    broker.set_secret(store, "token", "value-keyfile")
    key_file = store.path.parent / "broker" / ".master.key"
    assert key_file.is_file()
    assert len(bytes.fromhex(key_file.read_text(encoding="utf-8"))) == 32
    assert broker.get_secret(store, "token") == "value-keyfile"


# -- scopes, redaction, bookkeeping -------------------------------------------


def test_inject_resolves_only_scoped_names(store):
    broker.set_secret(store, "in_scope", "value-in-scope")
    broker.set_secret(store, "out_scope", "value-out-scope")

    out = broker.inject_secrets(store, {"path": "x", "secrets": ["in_scope"]}, ["in_scope"])
    assert out["secrets"] == {"in_scope": "value-in-scope"}
    assert out["path"] == "x"  # a copy; nothing else changes

    with pytest.raises(broker.BrokerError) as excinfo:
        broker.inject_secrets(store, {"secrets": ["out_scope"]}, ["in_scope"])
    assert "requires_scopes" in str(excinfo.value)


def test_inject_missing_secret_raises(store):
    with pytest.raises(broker.BrokerError) as excinfo:
        broker.inject_secrets(store, {"secrets": ["absent"]}, ["absent"])
    assert "not found" in str(excinfo.value)


def test_inject_updates_last_used(store):
    broker.set_secret(store, "token", "value-used")
    assert broker.secret_meta(store, "token")["last_used"] is None
    broker.inject_secrets(store, {"secrets": ["token"]}, ["token"])
    assert broker.secret_meta(store, "token")["last_used"] is not None


def test_redact_walks_strings_dicts_and_lists():
    secrets = {"short": "abcd", "longer": "abcdefgh"}
    payload = {
        "a": "x abcdefgh y",
        "b": ["abcd", 1, {"c": "abcd"}],
        2: None,
    }
    out = broker.redact(payload, secrets)
    assert out["a"] == "x [REDACTED:longer] y"
    assert out["b"][0] == "[REDACTED:short]"
    assert out["b"][2]["c"] == "[REDACTED:short]"
    assert broker.redact("clean", secrets) == "clean"
    assert broker.redact({"x": "y"}, {}) == {"x": "y"}


def test_known_secrets_skips_undecryptable_records(store):
    broker.set_secret(store, "good", "value-good")
    path = _record_path(store, "bad")
    path.write_text(json.dumps({"v": 1, "ct": "AA==", "nonce": "AA=="}), encoding="utf-8")
    assert broker.known_secrets(store) == {"good": "value-good"}
