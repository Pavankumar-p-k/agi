"""Reasoner tests: a local model proposes, the kernel still decides.

These run against a real (fake) HTTP server on 127.0.0.1, not a mocked
`urlopen`, so the wire contract — endpoint path, bearer header, structured
output request, response parsing — is exercised for real. What the server
returns is what a model would return: untrusted JSON, which the reasoner
validates before a plan can exist.

No test may reach a real model: conftest clears MJ_MODEL_* for every test.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from mj.brain import model as model_adapter
from mj.brain import planner, reasoner
from mj.core import audit, registry
from mj.core.store import Store
from mj.executor import capabilities as caps
from mj.executor import runner
from mj.world import probes as world_probes

CANARY_KEY = "sk-canary-0f9d4c1a7b2e-not-a-real-key"


# -- a real local HTTP server standing in for a model ------------------------


class _State:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.content: str = json.dumps({"steps": []})
        self.status: int = 200
        self.delay: float = 0.0
        self.lock = threading.Lock()


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - http.server API
        state: _State = self.server.state  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            body = {"_unparseable": raw.decode("utf-8", errors="replace")}
        with state.lock:
            state.requests.append(
                {"path": self.path, "headers": dict(self.headers), "body": body}
            )
        if state.delay:
            time.sleep(state.delay)
        if state.status != 200:
            self.send_response(state.status)
            self.send_header("Content-Length", "2")
            self.end_headers()
            try:
                self.wfile.write(b"{}")
            except OSError:
                pass
            return
        payload = json.dumps(
            {"choices": [{"message": {"content": state.content}}]}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except OSError:  # client gave up (timeout test)
            pass

    def log_message(self, *args: Any) -> None:
        return


class FakeModelServer:
    def __init__(self) -> None:
        self.state = _State()
        self.base_url = ""

    def __enter__(self) -> "FakeModelServer":
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._httpd.daemon_threads = True
        self._httpd.state = self.state  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        self.base_url = f"http://127.0.0.1:{self._httpd.server_port}/v1"
        return self

    def __exit__(self, *exc: Any) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)

    @property
    def requests(self) -> list[dict[str, Any]]:
        return self.state.requests

    def reply(self, *steps: dict[str, Any]) -> None:
        self.state.content = json.dumps({"steps": list(steps)})

    def reply_raw(self, content: str) -> None:
        self.state.content = content


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    s = Store.open(tmp_path)
    caps.ensure_registered(s)
    yield s
    s.close()


@pytest.fixture()
def fake_model(monkeypatch: pytest.MonkeyPatch) -> FakeModelServer:
    with FakeModelServer() as srv:
        monkeypatch.setenv("MJ_MODEL_PROVIDER", "ollama")
        monkeypatch.setenv("MJ_MODEL_BASE_URL", srv.base_url)
        monkeypatch.setenv("MJ_MODEL_NAME", "test-model")
        yield srv


def _step(step_id: str, capability_id: str, **kw: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"step_id": step_id, "capability_id": capability_id}
    out.update(kw)
    return out


def _last_audit(store: Store) -> dict[str, Any]:
    return audit.entries(store, limit=1)[0]


# -- the offline contract ----------------------------------------------------


def test_no_model_configured_means_no_call_and_the_same_question(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    def explode(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("a model must not be contacted when none is configured")

    monkeypatch.setattr(model_adapter, "chat_json", explode)
    with pytest.raises(planner.UnknownGoalError) as excinfo:
        planner.build_plan(store, "deploy to mars")
    assert called is False
    assert excinfo.value.question
    assert excinfo.value.reasoner_note is None


def test_known_intent_never_consults_the_model(
    store: Store, fake_model: FakeModelServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("deterministic goals must not depend on a model")

    monkeypatch.setattr(model_adapter, "chat_json", explode)
    plan = planner.build_plan(store, "how much disk space do I have?")
    assert plan.source == "deterministic"
    assert [s.capability_id for s in plan.steps] == ["os.facts"]
    assert fake_model.requests == []


def test_partially_configured_model_is_reported_not_ignored(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MJ_MODEL_PROVIDER", "ollama")
    monkeypatch.delenv("MJ_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("MJ_MODEL_NAME", raising=False)
    with pytest.raises(model_adapter.ModelError) as excinfo:
        model_adapter.config_from_env()
    assert "MJ_MODEL_BASE_URL" in str(excinfo.value)
    with pytest.raises(planner.UnknownGoalError) as excinfo:
        planner.build_plan(store, "deploy to mars")
    assert "MJ_MODEL_BASE_URL" in (excinfo.value.reasoner_note or "")
    status = model_adapter.status()
    assert status["configured"] is False and "error" in status


# -- the happy path: a reasoned plan is a normal, gated plan -----------------


def test_reasoned_plan_request_contract_and_end_to_end_run(
    store: Store, fake_model: FakeModelServer, tmp_path: Path
) -> None:
    sandbox = tmp_path / "downloads"
    sandbox.mkdir()
    for name in ("a.txt", "b.png", "c.unknownext"):
        (sandbox / name).write_text("payload", encoding="utf-8")
    fake_model.reply(
        _step("s1", "files.list", name="list downloads", inputs={"path": str(sandbox)}),
        _step(
            "s2",
            "files.organize.plan",
            name="propose categories",
            inputs={"path": str(sandbox)},
            depends_on=["s1"],
        ),
    )

    plan = planner.build_plan(store, "sort out the download folder", {"dir": str(sandbox)})

    assert plan.source == "reasoner:ollama:test-model"
    assert [s.step_id for s in plan.steps] == ["s1", "s2"]
    assert plan.steps[1].depends_on == ["s1"]
    assert plan.steps[0].inputs == {"path": str(sandbox)}

    # the wire contract: one OpenAI-compatible chat completion, schema-bound
    assert len(fake_model.requests) == 1
    request = fake_model.requests[0]
    assert request["path"] == "/v1/chat/completions"
    assert request["body"]["model"] == "test-model"
    assert request["body"]["stream"] is False
    rf = request["body"]["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["name"] == "mj_plan"
    assert rf["json_schema"]["strict"] is True
    assert [m["role"] for m in request["body"]["messages"]] == ["system", "user"]
    system_prompt = request["body"]["messages"][0]["content"]
    assert "files.organize.plan" in system_prompt
    assert "never invent" in system_prompt
    assert str(sandbox) in request["body"]["messages"][1]["content"]

    # same goal + same model answer => same plan id => same idempotency keys
    again = planner.build_plan(store, "sort out the download folder", {"dir": str(sandbox)})
    assert again.plan_id == plan.plan_id

    # ...and it executes like any other plan: gated, verified, reversible
    report = runner.run_plan(store, plan, auto_approve=True)
    assert report["state"] == "done"
    assert report["summary"] == "every step verified"
    assert sorted(p.name for p in sandbox.iterdir()) == ["a.txt", "b.png", "c.unknownext"]

    actions = {row["action"] for row in audit.entries(store, limit=100)}
    assert "plan.reasoned" in actions
    ok, count, problem = audit.verify(store)
    assert ok, problem
    assert count > 0


def test_reasoned_plan_is_still_policy_gated(
    store: Store, fake_model: FakeModelServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules_file = tmp_path / "policy.json"
    rules_file.write_text(json.dumps({"default_action": "deny", "rules": []}), encoding="utf-8")
    monkeypatch.setenv("MJ_POLICY", str(rules_file))
    fake_model.reply(_step("s1", "os.facts", inputs={"probes": ["disk"]}))

    plan = planner.build_plan(store, "tell me something only a model could plan")
    report = runner.run_plan(store, plan, auto_approve=True)
    assert report["state"] == "blocked" and report["denied_steps"] == ["s1"]


# -- rejections: everything the model says is untrusted ---------------------


def test_hallucinated_capability_is_rejected_and_audited(
    store: Store, fake_model: FakeModelServer
) -> None:
    fake_model.reply(_step("s1", "shell.exec", inputs={"command": "rm -rf /"}))
    with pytest.raises(planner.UnknownGoalError) as excinfo:
        planner.build_plan(store, "clean up this machine")
    note = excinfo.value.reasoner_note or ""
    assert "shell.exec" in note and "not offered" in note
    entry = _last_audit(store)
    assert entry["action"] == "plan.reasoner.declined"
    assert "shell.exec" in json.loads(entry["payload_json"])["reason"]


def test_unexpected_input_key_is_rejected(
    store: Store, fake_model: FakeModelServer, tmp_path: Path
) -> None:
    fake_model.reply(
        _step("s1", "files.list", inputs={"path": str(tmp_path), "secrets": ["spreadsheet_column"]})
    )
    with pytest.raises(planner.UnknownGoalError) as excinfo:
        planner.build_plan(store, "look at everything in this folder")
    assert "not accepted" in (excinfo.value.reasoner_note or "")


def test_secret_name_outside_the_capability_scope_is_rejected(
    store: Store, fake_model: FakeModelServer, tmp_path: Path
) -> None:
    csv = tmp_path / "rows.csv"
    csv.write_text("a,b\n1,2\n", encoding="utf-8")
    fake_model.reply(
        _step(
            "s1",
            "data.spreadsheet.summary",
            inputs={"path": str(csv), "secrets": ["MJ_BROKER_KEY"]},
        )
    )
    with pytest.raises(planner.UnknownGoalError) as excinfo:
        planner.build_plan(store, "summarize this spreadsheet with the stored credential")
    assert "not one of" in (excinfo.value.reasoner_note or "")


def test_forward_dependency_is_rejected(store: Store, fake_model: FakeModelServer) -> None:
    fake_model.reply(
        _step("s1", "os.facts", inputs={"probes": ["disk"]}, depends_on=["s2"]),
        _step("s2", "files.list", inputs={"path": "."}),
    )
    with pytest.raises(planner.UnknownGoalError) as excinfo:
        planner.build_plan(store, "do the impossible thing")
    assert "earlier step" in (excinfo.value.reasoner_note or "")


def test_operator_directory_cannot_be_replaced(
    store: Store, fake_model: FakeModelServer, tmp_path: Path
) -> None:
    fake_model.reply(_step("s1", "files.list", inputs={"path": str(tmp_path / "somewhere-else")}))
    with pytest.raises(planner.UnknownGoalError) as excinfo:
        planner.build_plan(store, "sort out these files", {"dir": str(tmp_path)})
    assert "explicit directory" in (excinfo.value.reasoner_note or "")


def test_empty_steps_is_an_honest_refusal(store: Store, fake_model: FakeModelServer) -> None:
    fake_model.reply()
    with pytest.raises(planner.UnknownGoalError) as excinfo:
        planner.build_plan(store, "book me a flight to tokyo")
    assert "declined" in (excinfo.value.reasoner_note or "")


def test_extra_top_level_key_is_rejected(store: Store, fake_model: FakeModelServer) -> None:
    fake_model.reply_raw(
        json.dumps(
            {
                "steps": [_step("s1", "os.facts", inputs={"probes": ["disk"]})],
                "policy": {"default_action": "allow"},
            }
        )
    )
    with pytest.raises(planner.UnknownGoalError) as excinfo:
        planner.build_plan(store, "change your own policy")
    assert "exactly one key" in (excinfo.value.reasoner_note or "")


# -- failures fall back to one question, never to a guess -------------------


def test_http_error_falls_back(store: Store, fake_model: FakeModelServer) -> None:
    fake_model.state.status = 500
    with pytest.raises(planner.UnknownGoalError) as excinfo:
        planner.build_plan(store, "deploy to mars")
    assert "HTTP 500" in (excinfo.value.reasoner_note or "")


def test_timeout_is_bounded_and_falls_back(
    store: Store, fake_model: FakeModelServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_model.state.delay = 0.7
    monkeypatch.setenv("MJ_MODEL_TIMEOUT_S", "0.2")
    started = time.monotonic()
    with pytest.raises(planner.UnknownGoalError) as excinfo:
        planner.build_plan(store, "deploy to mars")
    elapsed = time.monotonic() - started
    note = excinfo.value.reasoner_note or ""
    assert "TimeoutError" in note or "unreachable" in note
    assert elapsed < 5, f"the request deadline was not enforced ({elapsed:.2f}s)"


def test_prose_instead_of_json_falls_back(store: Store, fake_model: FakeModelServer) -> None:
    fake_model.reply_raw("Sure! Here is a lovely plan for you.")
    with pytest.raises(planner.UnknownGoalError) as excinfo:
        planner.build_plan(store, "deploy to mars")
    assert "no JSON object" in (excinfo.value.reasoner_note or "")


def test_fenced_json_is_tolerated(store: Store, fake_model: FakeModelServer) -> None:
    """Local servers sometimes wrap the object in fences; parse it, still validate."""
    body = json.dumps({"steps": [_step("s1", "os.facts", inputs={"probes": ["disk"]})]})
    fake_model.reply_raw(f"```json\n{body}\n```")
    plan = planner.build_plan(store, "anything the intents do not cover")
    assert [s.capability_id for s in plan.steps] == ["os.facts"]


# -- the key never leaks, the catalogue never lies ---------------------------


def test_api_key_is_sent_to_the_endpoint_but_never_recorded(
    store: Store, fake_model: FakeModelServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MJ_MODEL_API_KEY", CANARY_KEY)
    fake_model.reply(_step("s1", "os.facts", inputs={"probes": ["disk"]}))
    plan = planner.build_plan(store, "something only a model could plan")
    # sent as a bearer token...
    assert fake_model.requests[0]["headers"]["Authorization"] == f"Bearer {CANARY_KEY}"
    # ...and present nowhere the user, the audit log or a report can read
    assert CANARY_KEY not in json.dumps(plan.to_dict())
    assert CANARY_KEY not in json.dumps(audit.entries(store, limit=100))
    assert CANARY_KEY not in json.dumps(model_adapter.status())


def test_worker_subprocess_never_inherits_the_model_key(
    store: Store,
    fake_model: FakeModelServer,
    monkeypatch: pytest.MonkeyPatch,
    override_run: Any,
) -> None:
    """The key belongs to the reasoner alone; a step worker has no business with it."""
    monkeypatch.setenv("MJ_MODEL_API_KEY", CANARY_KEY)
    override_run(
        "os.facts",
        "def run(store, inputs):\n"
        "    import os\n"
        "    return {'sees_model_key': 'MJ_MODEL_API_KEY' in os.environ}\n",
    )
    plan = planner.build_plan(store, "disk")
    report = runner.run_plan(store, plan, auto_approve=True)
    row = store.one(
        "SELECT output_json FROM step_results WHERE task_id = ? AND step_id = 's1'",
        (report["task_id"],),
    )
    assert json.loads(row["output_json"]) == {"sees_model_key": False}


def test_catalogue_offers_only_healthy_capabilities(store: Store) -> None:
    ids = {entry["capability_id"] for entry in reasoner.catalogue(store)}
    assert ids == set(reasoner.INPUT_SCHEMAS)
    registry.set_status(store, "os.facts", "degraded")
    after = {entry["capability_id"] for entry in reasoner.catalogue(store)}
    assert "os.facts" not in after


def test_every_builtin_capability_has_a_declared_input_contract() -> None:
    """A new capability without a contract is simply not offered to the model."""
    missing = sorted(set(caps.BUILTINS) - set(reasoner.INPUT_SCHEMAS))
    assert missing == [], f"no input contract for {missing}: the reasoner cannot use them"


def test_probe_choices_match_the_world_probes() -> None:
    assert set(reasoner.PROBE_CHOICES) == set(world_probes.PROBES)


def test_model_status_is_readiness_only(fake_model: FakeModelServer) -> None:
    status = model_adapter.status()
    assert status["configured"] is True
    assert status["endpoint"].endswith("/v1/chat/completions")
    assert status["model"] == "test-model"
    assert status["api_key_set"] is False
    assert "api_key" not in status


def test_plan_schema_is_bounded() -> None:
    schema = reasoner.plan_schema(10_000)
    assert schema["properties"]["steps"]["maxItems"] == reasoner.SCHEMA_MAX_STEPS
    assert reasoner.plan_schema(0)["properties"]["steps"]["maxItems"] == 1
