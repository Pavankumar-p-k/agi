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
from __future__ import annotations

import asyncio
import json
import logging
import re
import time

from core.agent_helpers import (
    _ADMIN_SCHEMA_NAMES,
    _API_HOSTS,
    _MCP_KEYWORDS,
    _TOOL_SELECTION_TIMEOUT_SECONDS,
    _VERIFIER_EFFECTFUL_TOOLS,
    _VERIFIER_MAX_ROUNDS,
    _append_tool_results,
    _build_actions_snapshot,
    _detect_admin_intent,
    _empty_response_fallback,
    _extract_last_user_message,
    _load_mcp_disabled_map,
    _recent_context_for_retrieval,
    _resolve_tool_blocks,
    _run_verifier_subagent,
)
from core.agent_metrics import _compute_final_metrics
from core.agent_prompts import _build_system_prompt
from core.agent_tools import (
    FUNCTION_TOOL_SCHEMAS,
    execute_tool_block,
    format_tool_result,
    get_mcp_manager,
    strip_tool_blocks,
)
from core.graph.state import THINK_RE, AgentPhase, AgentState, RoundState
from core.llm_core import _is_ollama_native_url, stream_llm_with_fallback
from core.model_context import estimate_tokens
from core.settings_legacy import get_setting
from core.tools._constants import TOOL_TAGS, ToolBlock
from core.tools.browser_planner import BrowserPlanner
from core.tools.security import blocked_tools_for_owner

logger = logging.getLogger(__name__)


async def plan_node(state: AgentState) -> AgentState:
    """Run deterministic browser planner pre_plan on parsed tool blocks.

    Injects browser_snapshot after every browser_navigate so the LLM
    always receives page state without needing to ask for it.
    """
    from core.tools.browser_planner import BrowserPlanner

    rs = state.round_state
    if not rs or not rs.tool_blocks:
        state.phase = AgentPhase.TOOL_CALLING
        return state

    # Initialise planner context on first round
    if state.browser_planner_ctx is None:
        last_msg = _extract_last_user_message(state.messages) or ""
        state.browser_planner_ctx = BrowserPlanner.init(last_msg)

    # Run pre_plan to inject snapshot after navigate
    planned, updated_ctx = BrowserPlanner.pre_plan(rs.tool_blocks, state.browser_planner_ctx)
    rs.tool_blocks = planned
    state.browser_planner_ctx = updated_ctx

    state.phase = AgentPhase.TOOL_CALLING
    return state


def _lookup_endpoint_supports(SL, ME, endpoint_url):
    """Thunk for asyncio.to_thread to avoid blocking event loop with sync DB query."""
    _db = SL()
    try:
        ep = _db.query(ME).filter(ME.base_url == endpoint_url).first()
        if not ep and endpoint_url:
            u = endpoint_url.rstrip("/")
            ep = _db.query(ME).filter(ME.base_url == u).first() or \
                 _db.query(ME).filter(ME.base_url == u + "/").first()
        return ep
    finally:
        _db.close()


async def setup_node(state: AgentState) -> AgentState:
    mcp_mgr = get_mcp_manager()
    state.mcp_mgr = mcp_mgr
    state.disabled_tools_set = set(state.disabled_tools or [])
    public_blocked_tools = blocked_tools_for_owner(state.owner)
    if public_blocked_tools:
        state.disabled_tools_set.update(public_blocked_tools)
        mcp_mgr = None
        state.mcp_mgr = None

    _t0 = time.time()
    state.needs_admin = _detect_admin_intent(state.messages)
    state.last_user = _extract_last_user_message(state.messages)
    state.retrieval_query = _recent_context_for_retrieval(state.messages) or state.last_user
    state.mcp_disabled_map = _load_mcp_disabled_map() if mcp_mgr else {}
    state.prep_timings["request_setup"] = time.time() - _t0

    _t1 = time.time()
    if state.relevant_tools:
        state.relevant_tools_set = set(state.relevant_tools)
        logger.info(f"[tool-rag] Using caller-provided relevant_tools ({len(state.relevant_tools)} tools): {sorted(state.relevant_tools)[:10]}")
    if not state.relevant_tools:
        try:
            from core.tools.index import ALWAYS_AVAILABLE, get_tool_index
            tool_idx = get_tool_index()
            if tool_idx:
                if mcp_mgr:
                    try:
                        await asyncio.wait_for(
                            asyncio.to_thread(tool_idx.index_mcp_tools, mcp_mgr, state.mcp_disabled_map),
                            timeout=_TOOL_SELECTION_TIMEOUT_SECONDS,
                        )
                    except TimeoutError:
                        logger.warning(
                            "[tool-rag] MCP tool indexing exceeded %.1fs; continuing without reindex",
                            _TOOL_SELECTION_TIMEOUT_SECONDS,
                        )
                if state.retrieval_query:
                    try:
                        state.relevant_tools_set = await asyncio.wait_for(
                            asyncio.to_thread(tool_idx.get_tools_for_query, state.retrieval_query, 8),
                            timeout=_TOOL_SELECTION_TIMEOUT_SECONDS,
                        )
                        logger.info(f"[tool-rag] Retrieved tools for query: {sorted(state.relevant_tools_set - ALWAYS_AVAILABLE)}")
                    except TimeoutError:
                        logger.warning(
                            "[tool-rag] Retrieval exceeded %.1fs; falling back to always-available tools",
                            _TOOL_SELECTION_TIMEOUT_SECONDS,
                        )
                        state.relevant_tools_set = set(ALWAYS_AVAILABLE)
        except Exception as e:
            logger.warning(f"[tool-rag] Retrieval failed, using keyword fallback: {e}")
            state.relevant_tools_set = None

    if not state.relevant_tools_set and state.retrieval_query:
        from core.tools.index import ALWAYS_AVAILABLE, ToolIndex
        state.relevant_tools_set = set(ALWAYS_AVAILABLE)
        ql = state.retrieval_query.lower()
        for keywords, tools in ToolIndex._KEYWORD_HINTS.items():
            if any(kw in ql for kw in keywords):
                state.relevant_tools_set.update(tools)
        state.relevant_tools_set.update({"create_document", "manage_memory", "manage_notes"})
        logger.info(f"[tool-rag] Keyword fallback selected: {sorted(state.relevant_tools_set - ALWAYS_AVAILABLE)}")

    if state.relevant_tools_set is not None and state.active_document is not None:
        state.relevant_tools_set.update({"edit_document", "update_document", "suggest_document"})

    state.prep_timings["tool_selection"] = time.time() - _t1

    _t2 = time.time()
    _model_lc = (state.model or "").lower()
    _endpoint_supports: bool | None = None
    try:
        from core.database_models import ModelEndpoint as _ME
        from core.database_models import SessionLocal as _SL
        _ep = await asyncio.to_thread(_lookup_endpoint_supports, _SL, _ME, state.endpoint_url)
        if _ep is not None:
            _endpoint_supports = _ep.supports_tools
    except Exception as _e:
        logger.debug(f"endpoint supports_tools lookup failed: {_e}")
    _model_supports_tools = any(kw in _model_lc for kw in (
        "gpt-4", "gpt-5", "gpt-o", "claude", "gemini", "gemma",
        "qwen3", "qwen2.5", "mixtral", "mistral", "llama-3.1", "llama-3.2",
        "llama-3.3", "llama-4",
        "minimax", "kimi", "yi-", "phi-3", "phi-4", "command-r",
        "glm-4", "internlm", "hermes",
        "deepseek-v", "deepseek-chat",
    ))
    _model_no_tools = any(kw in _model_lc for kw in ("deepseek-r1",))
    _is_ollama_native = _is_ollama_native_url(state.endpoint_url or "")
    if _endpoint_supports is True:
        state.is_api_model = True
    elif _endpoint_supports is False or _model_no_tools or _is_ollama_native:
        state.is_api_model = False
    else:
        state.is_api_model = any(h in state.endpoint_url for h in _API_HOSTS) or _model_supports_tools

    # Skip expensive context building for simple chat requests
    _mode_val = state.mode.value if hasattr(state.mode, 'value') else str(state.mode or "")
    _is_chat = _mode_val in ("chat", "direct")
    _codebase_context = ""
    _repomap = ""
    _code_graph_context = ""
    if not _is_chat and state.retrieval_query:
        try:
            from core.codebase_indexer import search_codebase
            _codebase_context = search_codebase(state.retrieval_query, k=3, owner=state.owner)
        except Exception as e:
            logger.warning("[core.graph.nodes] execute_node failed: %s", e)
    if not _is_chat:
        try:
            from pathlib import Path

            from core.repomap import build_repomap
            _repomap = build_repomap(Path.cwd())
        except Exception as e:
            logger.warning("[core.graph.nodes] execute_node failed: %s", e)
    if not _is_chat and state.retrieval_query:
        try:
            from core.code_graph import get_code_graph
            cg = get_code_graph()
            if cg:
                _code_graph_context = cg.format_for_prompt(state.retrieval_query, top_n=8)
        except Exception as e:
            logger.warning("[core.graph.nodes] execute_node failed: %s", e)
    if _is_chat:
        logger.info("[PROFILE] skipped heavy context (chat mode, saved ~%.0fs)", time.time() - _t2)

    if state.session_id:
        try:
            from core.session_db import get_recent_snapshots
            _prev = get_recent_snapshots(exclude_session=state.session_id, limit=5)
            if _prev:
                _lines = ["Previous session summaries:"]
                for _p in _prev:
                    _p_sid = _p.get("session_id", "?")[:12]
                    _p_summary = _p.get("summary", "")
                    if _p_summary:
                        _lines.append(f"  [{_p_sid}] {_p_summary}")
                _previous_sessions_text = "\n".join(_lines)
                _prev_user_msg = next((m for m in reversed(state.messages) if m.get("role") == "user"), None)
                if _prev_user_msg:
                    _prev_user_msg["content"] = (
                        _previous_sessions_text
                        + "\n\n---\n\n"
                        + _prev_user_msg["content"]
                    )
        except Exception as _e:
            logger.debug("[session-db] previous sessions load skipped: %s", _e)

    messages, state.mcp_schemas = _build_system_prompt(
        state.messages, state.model, state.active_document, mcp_mgr,
        state.disabled_tools_set,
        needs_admin=state.needs_admin, relevant_tools=state.relevant_tools_set,
        mcp_disabled_map=state.mcp_disabled_map,
        compact=state.is_api_model,
        owner=state.owner,
        codebase_context=_codebase_context,
        repomap=_repomap,
        code_graph_context=_code_graph_context,
    )
    state.messages = messages
    state.prep_timings["prompt_build"] = time.time() - _t2

    _t3 = time.time()
    try:
        from core.context_compactor import trim_for_context

        from core.context_budget import TokenBudget, compute_input_token_budget
        soft_budget = int(get_setting("agent_input_token_budget", 6000) or 0)
        if soft_budget > 0:
            before_trim_tokens = estimate_tokens(state.messages)
            try:
                hard_max = int(get_setting("agent_input_token_hard_max", 24000) or 24000)
            except (TypeError, ValueError):
                hard_max = 24000
            if hard_max <= 0:
                hard_max = 24000
            budget: TokenBudget = compute_input_token_budget(soft_budget, state.context_length, False, hard_max=hard_max)
            trimmed_messages = trim_for_context(state.messages, budget)
            after_trim_tokens = estimate_tokens(trimmed_messages)
            if after_trim_tokens < before_trim_tokens:
                logger.info(
                    "[agent] soft-trimmed context: %s -> %s tokens (budget=%s)",
                    before_trim_tokens, after_trim_tokens, budget.total,
                )
                state.messages = trimmed_messages
    except Exception as e:
        logger.warning("[agent] Soft context trim skipped: %s", e)
    state.prep_timings["context_trim"] = time.time() - _t3

    state.messages = [{k: v for k, v in msg.items() if k != "_protected"} for msg in state.messages]
    state.total_start = time.time()
    state.verifier_instruction = _extract_last_user_message(state.messages)
    state.phase = AgentPhase.THINKING

    _total_prep = time.time() - _t0
    logger.info("[PROFILE] setup_node total=%.3fs breakdown=%s",
        _total_prep, {k: round(v, 3) for k, v in state.prep_timings.items()})
    state.events.append(
        f'data: {json.dumps({"type":"phase_change","phase":"setup_complete","prep":{k:round(v,3) for k,v in state.prep_timings.items()}})}\n\n'
    )

    state.events.append(
        f'data: {json.dumps({"type": "agent_prep", "data": {k: round(v, 3) for k, v in state.prep_timings.items()}})}\n\n'
    )
    return state


async def think_node(state: AgentState) -> AgentState:
    round_num = state.round_num + 1
    state.round_num = round_num
    round_response = ""
    round_reasoning = ""
    native_tool_calls = []
    state.doc_acc = ""
    state.doc_opened = False
    state.doc_last_len = 0
    state.doc_fence_offset = 0
    state.doc_scan_from = 0

    if state.force_answer:
        all_tool_schemas = []
    elif state.is_api_model:
        relevant = state.relevant_tools_set
        if relevant:
            base_schemas = [
                s for s in FUNCTION_TOOL_SCHEMAS
                if s.get("function", {}).get("name") in relevant
            ]
            mcp_filtered = [
                s for s in state.mcp_schemas
                if s.get("function", {}).get("name") in relevant
            ]
            all_tool_schemas = base_schemas + mcp_filtered
        else:
            base_schemas = FUNCTION_TOOL_SCHEMAS if state.needs_admin else [
                s for s in FUNCTION_TOOL_SCHEMAS
                if s.get("function", {}).get("name") not in _ADMIN_SCHEMA_NAMES
            ]
            all_tool_schemas = base_schemas + state.mcp_schemas
        if state.disabled_tools_set:
            all_tool_schemas = [
                t for t in all_tool_schemas
                if t.get("function", {}).get("name") not in state.disabled_tools_set
                and t.get("name") not in state.disabled_tools_set
            ]
    else:
        relevant = state.relevant_tools_set
        if relevant:
            base_schemas = [
                s for s in FUNCTION_TOOL_SCHEMAS
                if s.get("function", {}).get("name") in relevant
            ]
            mcp_filtered = [
                s for s in state.mcp_schemas
                if s.get("function", {}).get("name") in relevant
            ]
            all_tool_schemas = base_schemas + mcp_filtered
        else:
            base_schemas = FUNCTION_TOOL_SCHEMAS if state.needs_admin else [
                s for s in FUNCTION_TOOL_SCHEMAS
                if s.get("function", {}).get("name") not in _ADMIN_SCHEMA_NAMES
            ]
            all_tool_schemas = base_schemas + state.mcp_schemas
        if state.disabled_tools_set:
            all_tool_schemas = [
                t for t in all_tool_schemas
                if t.get("function", {}).get("name") not in state.disabled_tools_set
                and t.get("name") not in state.disabled_tools_set
            ]

    agent_stream_timeout = int(get_setting("agent_stream_timeout_seconds", 300) or 300)
    _tool_names_sent = [t.get("function", {}).get("name") for t in (all_tool_schemas or []) if t.get("function")]
    logger.info(
        f"[agent-debug] round={round_num} model={state.model} "
        f"_is_api_model={state.is_api_model} "
        f"tools_sent={len(_tool_names_sent)} "
        f"tool_names={_tool_names_sent[:15]} "
        f"relevant_tools={sorted(state.relevant_tools_set)[:15] if state.relevant_tools_set else 'ALL'}"
    )

    state.candidates = [(state.endpoint_url, state.model, state.headers)] + list(state.fallbacks or [])
    _round_deadline = time.time() + max(agent_stream_timeout * 4, 1200)

    async for chunk in stream_llm_with_fallback(
        state.candidates,
        state.messages,
        temperature=state.temperature,
        max_tokens=state.max_tokens,
        prompt_type=state.prompt_type if round_num == 1 else None,
        tools=all_tool_schemas if all_tool_schemas else None,
        timeout=agent_stream_timeout,
    ):
        if time.time() > _round_deadline:
            logger.warning(f"[agent] round {round_num} stream exceeded wall-clock deadline; cutting off")
            break
        if chunk.startswith("event: error"):
            state.events.append(chunk)
            continue
        if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
            try:
                data = json.loads(chunk[6:])
                if data.get("type") == "tool_call_delta":
                    logger.debug(f"tool_call_delta: name={data.get('name')}, len(arg_delta)={len(data.get('arg_delta', ''))}")
                    state.doc_acc += data.get("arg_delta", "")
                    if not state.doc_opened:
                        tm = re.search(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"', state.doc_acc)
                        if tm:
                            state.doc_opened = True
                            try:
                                title = json.loads('"' + tm.group(1) + '"')
                            except Exception as _e:
                                logger.debug("doc title parse fallback: %s", _e)
                                title = tm.group(1)
                            lm = re.search(r'"language"\s*:\s*"((?:[^"\\]|\\.)*)"', state.doc_acc)
                            lang = ""
                            if lm:
                                try:
                                    lang = json.loads('"' + lm.group(1) + '"')
                                except Exception as _e:
                                    logger.debug("doc lang parse fallback: %s", _e)
                                    lang = lm.group(1)
                            logger.info(f"Doc streaming: open title={title!r} lang={lang!r}")
                            state.events.append(
                                f'data: {json.dumps({"type": "doc_stream_open", "title": title, "language": lang})}\n\n'
                            )
                    if state.doc_opened:
                        cm = re.search(r'"content"\s*:\s*"', state.doc_acc)
                        if cm:
                            raw = state.doc_acc[cm.end():]
                            raw = re.sub(r'"\s*\}\s*$', '', raw)
                            try:
                                decoded = json.loads('"' + raw + '"')
                            except Exception as _e1:
                                logger.debug("doc content parse fallback: %s", _e1)
                                try:
                                    decoded = json.loads('"' + raw.rstrip('\\') + '"')
                                except Exception as _e2:
                                    logger.debug("doc content raw fallback: %s", _e2)
                                    decoded = raw.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')
                            if len(decoded) > state.doc_last_len:
                                state.doc_last_len = len(decoded)
                                state.events.append(
                                    f'data: {json.dumps({"type": "doc_stream_delta", "content": decoded})}\n\n'
                                )
                elif data.get("type") == "tool_calls":
                    native_tool_calls = data.get("calls", [])
                    logger.info(f"Agent round {round_num}: received {len(native_tool_calls)} native tool call(s)")
                    state.events.append(chunk)
                elif data.get("type") == "usage":
                    u = data.get("data", {})
                    round_input = u.get("input_tokens", 0)
                    state.real_input_tokens += round_input
                    state.real_output_tokens += u.get("output_tokens", 0)
                    state.last_round_input_tokens = round_input
                    state.has_real_usage = True
                    if u.get("gen_tps"):
                        state.backend_gen_tps = u["gen_tps"]
                    if u.get("prefill_tps"):
                        state.backend_prefill_tps = u["prefill_tps"]
                elif data.get("type") == "fallback":
                    logger.warning(
                        f"[agent] round {round_num} fell back: "
                        f"{data.get('selected_model')} -> {data.get('answered_by')}"
                    )
                    state.events.append(chunk)
                elif "delta" in data:
                    if not state.first_token_received:
                        state.time_to_first_token = time.time() - state.total_start
                        state.first_token_received = True
                    if data.get("thinking"):
                        round_reasoning += data["delta"]
                    else:
                        round_response += data["delta"]
                        state.full_response += data["delta"]
                    state.events.append(chunk)
                    if round_num > 1 and not state.doc_acc:
                        _fence_marker = '```create_document\n'
                        if not state.doc_opened and _fence_marker in round_response[state.doc_scan_from:]:
                            _fi = round_response.index(_fence_marker, state.doc_scan_from)
                            _fa = round_response[_fi + len(_fence_marker):]
                            _fl = _fa.split('\n')
                            if _fl and _fl[0].strip():
                                state.doc_opened = True
                                _ft = _fl[0].strip()
                                _kl = {'python','py','javascript','js','typescript','ts','html','css','json','yaml','bash','sql','rust','go','java','c','cpp','markdown','text'}
                                _flang = _fl[1].strip() if len(_fl) > 1 and _fl[1].strip().lower() in _kl else ''
                                state.doc_fence_offset = _fi + len(_fence_marker) + len(_fl[0]) + 1
                                if _flang:
                                    state.doc_fence_offset += len(_fl[1]) + 1
                                state.doc_last_len = 0
                                state.events.append(
                                    f'data: {json.dumps({"type": "doc_stream_open", "title": _ft, "language": _flang})}\n\n'
                                )
                        if state.doc_opened:
                            _rc = round_response[state.doc_fence_offset:]
                            _ci = _rc.find('\n```')
                            if _ci >= 0:
                                _rc = _rc[:_ci]
                            if len(_rc) > state.doc_last_len:
                                state.doc_last_len = len(_rc)
                                state.events.append(
                                    f'data: {json.dumps({"type": "doc_stream_delta", "content": _rc})}\n\n'
                                )
                            if _ci >= 0:
                                state.doc_opened = False
                                state.doc_scan_from = state.doc_fence_offset + _ci + len('\n```')
                                state.doc_fence_offset = 0
                                state.doc_last_len = 0
                elif data.get("error"):
                    err_msg = data.get("error", "unknown")
                    logger.error(f"Agent round {round_num}: stream error: {err_msg}")
                    state.events.append(
                        f'data: {json.dumps({"delta": chr(10) + chr(10) + "*[Stream error: " + str(err_msg) + "]*"})}\n\n'
                    )
            except json.JSONDecodeError:
                if round_num == 1:
                    state.events.append(chunk)
        elif chunk.startswith("event: "):
            state.events.append(chunk)

    state.round_state = RoundState(
        round_num=round_num,
        response=round_response,
        reasoning=round_reasoning,
        native_tool_calls=native_tool_calls,
    )

    # Structured reasoning trace extraction
    reasoning_traces = []
    for t in THINK_RE.findall(round_response):
        reasoning_traces.append({
            "type": "reasoning_block",
            "content": t.strip()[:500],
        })

    _conf_re = re.compile(
        r'(?:confidence|confident|certainty|sure)\s*[:=]\s*(\d+(?:\.\d+)?)%?',
        re.IGNORECASE,
    )
    for cm in _conf_re.finditer(round_response):
        reasoning_traces.append({
            "type": "confidence_score",
            "value": float(cm.group(1)),
            "context": round_response[max(0, cm.start() - 40):cm.end() + 40],
        })

    if re.search(r'(?:alternative|instead|another option|could also)', round_response, re.IGNORECASE):
        reasoning_traces.append({
            "type": "alternatives_considered",
            "round": round_num,
        })

    if reasoning_traces:
        state.structured_reasoning.extend(reasoning_traces)
        state.events.append(
            'data: ' + json.dumps({
                "type": "reasoning_trace",
                "round": round_num,
                "traces": reasoning_traces,
            }) + '\n\n'
        )

    state.phase = AgentPhase.THINKING
    return state


async def route_node(state: AgentState) -> AgentState:
    rs = state.round_state
    if not rs:
        state.phase = AgentPhase.FINISHED
        return state

    tool_blocks, used_native = _resolve_tool_blocks(
        rs.response, rs.native_tool_calls, rs.round_num
    )
    rs.tool_blocks = tool_blocks

    if state.force_answer:
        if tool_blocks:
            logger.info(f"[agent] force-answer round {state.round_num}: discarding {len(tool_blocks)} ignored tool call(s)")
        rs.tool_blocks = []
        if not THINK_RE.sub("", strip_tool_blocks(rs.response)).strip():
            state.phase = AgentPhase.FORCE_ANSWER
            return state

    has_doc_tool = any(
        b.tool_type in ("create_document", "update_document")
        for b in tool_blocks
    ) or any(
        tc.get("name") in ("create_document", "update_document")
        for tc in rs.native_tool_calls
    )
    if not has_doc_tool and state.session_id and "create_document" not in (state.disabled_tools_set or set()):
        _code_block_re = re.compile(r'```(\w*)\n([\s\S]*?)```')
        for m in _code_block_re.finditer(rs.response):
            lang_tag = m.group(1).lower()
            code_body = m.group(2).strip()
            if code_body.count('\n') < 30:
                continue
            if lang_tag in TOOL_TAGS:
                continue
            lang_map = {"py": "python", "js": "javascript", "ts": "typescript", "": "text"}
            doc_lang = lang_map.get(lang_tag, lang_tag or "text")
            doc_title = f"Code ({doc_lang})"
            tb = ToolBlock("create_document", f"{doc_title}\n{doc_lang}\n{code_body}")
            rs.tool_blocks.append(tb)
            state.events.append(
                f'data: {json.dumps({"type": "doc_stream_open", "title": doc_title, "language": doc_lang})}\n\n'
            )
            state.events.append(
                f'data: {json.dumps({"type": "doc_stream_delta", "content": code_body})}\n\n'
            )
            logger.info(f"Auto-created document from {lang_tag} code block ({code_body.count(chr(10))+1} lines)")
            break

    cleaned_round = strip_tool_blocks(rs.response).strip()
    state.round_texts.append(cleaned_round)

    if not rs.tool_blocks:
        _claimed_done = bool(THINK_RE.sub("", cleaned_round).strip())
        if (state.effectful_used and not state.force_answer
                and _claimed_done
                and state.verifier_rounds < _VERIFIER_MAX_ROUNDS
                and get_setting("agent_verifier_subagent", False)):
            state.phase = AgentPhase.VERIFYING
            state.events.append(
                f'data: {json.dumps({"type": "agent_step", "round": state.round_num})}\n\n'
            )
            return state
        state.phase = AgentPhase.FINISHED
        return state

    sig = "|".join(sorted(f"{b.tool_type}:{(b.content or '').strip()[:120]}" for b in rs.tool_blocks))
    is_repeat = sig in state.recent_call_sigs
    state.recent_call_sigs.append(sig)
    for _b in rs.tool_blocks:
        state.tool_type_counts[_b.tool_type] += 1
    _real_text = THINK_RE.sub("", cleaned_round).strip()
    if is_repeat and not _real_text:
        state.stuck_rounds += 1
    else:
        state.stuck_rounds = 0

    is_stuck, reason = state.is_stuck()
    if is_stuck:
        logger.warning(
            f"[agent] loop-breaker tripped on round {state.round_num} ({reason}); "
            f"sig={sig[:80]!r}"
        )
        _off = [t for t in ("web_search", "bash")
                if state.disabled_tools_set and t in state.disabled_tools_set]
        _off_note = (f" ({', '.join(_off)} is currently disabled — say so if "
                     f"you needed it.)" if _off else "")
        state.force_answer = True
        state.messages.append({
            "role": "system",
            "content": (
                "You're repeating tool calls without converging. STOP calling "
                "tools and end the turn one of two ways: (a) write your best "
                "final answer NOW from the information already gathered, or "
                "(b) if you're genuinely blocked, say plainly what's blocking "
                "you in a sentence or two." + _off_note
            ),
        })
        state.full_response += "\n\n"
        state.events.append(
            f'data: {json.dumps({"type": "agent_step", "round": state.round_num + 1})}\n\n'
        )
        state.phase = AgentPhase.THINKING
        return state

    if not state.doc_opened and state.round_num == 1:
        for block in rs.tool_blocks:
            if block.tool_type == "create_document":
                state.doc_opened = True
                break

    if not state.doc_opened:
        for block in rs.tool_blocks:
            if block.tool_type == "create_document":
                lines = block.content.strip().split("\n")
                title = lines[0].strip() if lines else "Untitled"
                lang = ""
                content_start = 1
                if len(lines) > 1 and len(lines[1].strip()) < 20 and lines[1].strip().isalpha():
                    lang = lines[1].strip()
                    content_start = 2
                content = "\n".join(lines[content_start:]) if len(lines) > content_start else ""
                state.events.append(
                    f'data: {json.dumps({"type": "doc_stream_open", "title": title, "language": lang})}\n\n'
                )
                if content:
                    state.events.append(
                        f'data: {json.dumps({"type": "doc_stream_delta", "content": content})}\n\n'
                    )
                break
            elif block.tool_type == "update_document":
                content = block.content.strip()
                state.events.append(
                    f'data: {json.dumps({"type": "doc_stream_open", "title": "", "language": ""})}\n\n'
                )
                state.events.append(
                    f'data: {json.dumps({"type": "doc_stream_delta", "content": content})}\n\n'
                )
                break

    state.phase = AgentPhase.TOOL_CALLING
    return state


async def _execute_one_tool(
    state: AgentState, block: ToolBlock, idx: int,
) -> dict:
    """Execute a single tool block and return all result data."""
    is_doc_tool = block.tool_type in ("create_document", "update_document", "edit_document", "suggest_document")
    cmd_display = block.content.split("\n")[0].strip()[:80] if is_doc_tool else block.content.strip()

    _progress_q: asyncio.Queue = asyncio.Queue()

    async def _push(payload):
        await _progress_q.put(payload)

    async def _run():
        try:
            return await execute_tool_block(
                block, session_id=state.session_id,
                disabled_tools=state.disabled_tools_set,
                owner=state.owner, progress_cb=_push,
            )
        finally:
            await _progress_q.put(None)

    task = asyncio.create_task(_run())
    progress_events = []
    while True:
        evt = await _progress_q.get()
        if evt is None:
            break
        progress_events.append(evt)
    desc, result = await task

    _src_text = result.get("output") or result.get("results") or result.get("stdout") or ""
    if block.tool_type == "web_search" and _src_text:
        _src_marker = "<!-- SOURCES:"
        _src_idx = _src_text.find(_src_marker)
        if _src_idx >= 0:
            _src_end = _src_text.find(" -->", _src_idx)
            if _src_end >= 0:
                try:
                    _extracted_sources = json.loads(_src_text[_src_idx + len(_src_marker):_src_end])
                    progress_events.append({"type": "web_sources", "data": _extracted_sources})
                    _clean = _src_text[:_src_idx].rstrip()
                    if "output" in result:
                        result["output"] = _clean
                    elif "results" in result:
                        result["results"] = _clean
                    elif "stdout" in result:
                        result["stdout"] = _clean
                except (json.JSONDecodeError, Exception):
                    pass

    output_text = ""
    if is_doc_tool and "action" in result:
        action = result["action"]
        title = result.get("title", "")
        ver = result.get("version", "?")
        if action == "create":
            output_text = f'Document created: "{title}" (v{ver})'
        elif action == "edit":
            output_text = f'Document edited: "{title}" (v{ver}, {result.get("applied", 0)} edit(s))'
        elif action == "update":
            output_text = f'Document updated: "{title}" (v{ver})'
    elif "stdout" in result:
        output_text = (result["stdout"] or result["stderr"] or result.get("error", ""))[:2000]
    elif "output" in result:
        output_text = (result["output"] or "")[:2000]
    elif "response" in result:
        label = result.get("model", result.get("session_name", "AI"))
        output_text = f"{label}: {result['response']}"[:4000]
    elif "content" in result:
        output_text = result["content"][:2000]
    elif "results" in result:
        output_text = result["results"][:4000]
    elif "session_id" in result and "name" in result:
        output_text = f"Session created: {result['name']} (id: {result['session_id']})"
    elif "success" in result:
        output_text = (
            f"Written: {result.get('path', '')}"
            if result["success"]
            else f"Error: {result.get('error', '')}"
        )
    elif "error" in result:
        output_text = result["error"][:2000]

    return {
        "idx": idx,
        "desc": desc,
        "result": result,
        "block": block,
        "cmd_display": cmd_display,
        "is_doc_tool": is_doc_tool,
        "output_text": output_text,
        "progress_events": progress_events,
    }


async def tool_call_node(state: AgentState) -> AgentState:
    rs = state.round_state
    if not rs or not rs.tool_blocks:
        state.phase = AgentPhase.THINKING
        return state

    if state.max_tool_calls > 0 and state.total_tool_calls >= state.max_tool_calls:
        state.events.append(
            f'data: {json.dumps({"type": "budget_exceeded", "limit": state.max_tool_calls, "used": state.total_tool_calls})}\n\n'
        )
        state.phase = AgentPhase.FINISHED
        return state

    # Emit tool_start events in order immediately
    block_displays = []
    for block in rs.tool_blocks:
        is_doc = block.tool_type in ("create_document", "update_document", "edit_document", "suggest_document")
        cmd = block.content.split("\n")[0].strip()[:80] if is_doc else block.content.strip()
        block_displays.append(cmd)
        state.events.append(
            f'data: {json.dumps({"type": "tool_start", "tool": block.tool_type, "command": cmd, "round": state.round_num})}\n\n'
        )

    # Execute all tool blocks concurrently
    tasks = [_execute_one_tool(state, block, i) for i, block in enumerate(rs.tool_blocks)]
    results = await asyncio.gather(*tasks)

    # Post-plan loop: deterministic planner analyzes results and may inject new blocks
    # (search-fill, result-detection, loop-breaker, login-detection)
    _max_post_plan_iters = 5
    _pp_blocks: list[ToolBlock] = list(rs.tool_blocks)  # blocks for current iteration only
    for _ppi in range(_max_post_plan_iters):
        _extra_blocks, _updated_ctx = BrowserPlanner.post_plan(
            [r["result"] for r in results],
            _pp_blocks,
            state.browser_planner_ctx or {},
        )
        state.browser_planner_ctx = _updated_ctx
        if not _extra_blocks:
            break
        _offset = len(results)
        for _eb in _extra_blocks:
            is_doc = _eb.tool_type in ("create_document", "update_document", "edit_document", "suggest_document")
            cmd = _eb.content.split("\n")[0].strip()[:80] if is_doc else _eb.content.strip()
            state.events.append(
                f'data: {json.dumps({"type": "tool_start", "tool": _eb.tool_type, "command": cmd, "round": state.round_num, "planner": True})}\n\n'
            )
        _new_tasks = [_execute_one_tool(state, _eb, _offset + i) for i, _eb in enumerate(_extra_blocks)]
        _new_results = await asyncio.gather(*_new_tasks)
        results.extend(_new_results)
        rs.tool_blocks.extend(_extra_blocks)
        _pp_blocks = list(_extra_blocks)  # next iteration only sees newly injected blocks

    # Flush per-tool progress events as they arrive (already in state.events)
    # Process results in index order for deterministic tool_output ordering
    tool_results = []
    tool_result_texts = []
    for r in sorted(results, key=lambda x: x["idx"]):
        block = r["block"]
        result = r["result"]
        cmd_display = r["cmd_display"]
        is_doc_tool = r["is_doc_tool"]
        output_text = r["output_text"]

        # Flush progress events gathered during execution
        for pe in r["progress_events"]:
            if isinstance(pe, dict) and pe.get("type") == "web_sources":
                state.events.append(
                    f'data: {json.dumps({"type": "web_sources", "data": pe["data"]})}\n\n'
                )
            else:
                state.events.append(
                    f'data: {json.dumps({"type": "tool_progress", "tool": block.tool_type, "round": state.round_num, **pe})}\n\n'
                )

        if is_doc_tool and "action" in result:
            if result["action"] == "suggest":
                state.events.append(
                    f'data: {json.dumps({"type": "doc_suggestions", "doc_id": result["doc_id"], "suggestions": result["suggestions"]})}\n\n'
                )
            else:
                state.events.append(
                    f'data: {json.dumps({"type": "doc_update", "doc_id": result["doc_id"], "content": result["content"], "version": result["version"], "title": result.get("title", ""), "language": result.get("language")})}\n\n'
                )

        if "ui_event" in result:
            state.events.append(
                f'data: {json.dumps({"type": "ui_control", "data": result})}\n\n'
            )

        tool_output_data = {
            "type": "tool_output",
            "tool": block.tool_type,
            "command": cmd_display,
            "output": output_text,
            "exit_code": result.get("exit_code"),
        }
        if "ui_event" in result:
            tool_output_data["ui_event"] = result["ui_event"]
            for k in ("toggle_name", "state", "mode", "model", "endpoint_url", "theme_name", "colors"):
                if k in result:
                    tool_output_data[k] = result[k]
        for k in ("image_url", "image_prompt", "image_model", "image_size", "image_quality"):
            if k in result:
                tool_output_data[k] = result[k]
        if result.get("images"):
            img = result["images"][0]
            tool_output_data["screenshot"] = f"data:{img['mimeType']};base64,{img['data']}"
        state.events.append(f'data: {json.dumps(tool_output_data)}\n\n')

        if block.tool_type in ("create_document", "update_document", "edit_document") and result.get("doc_id"):
            state.events.append(
                'data: ' + json.dumps({
                    "type": "doc_update",
                    "doc_id": result["doc_id"],
                    "title": result.get("title", ""),
                    "language": result.get("language", ""),
                    "content": result.get("content", ""),
                    "version": result.get("version", 1),
                }) + '\n\n'
            )

        _rsid = result.get("research_session_id")
        if _rsid:
            _anchor = f"\n\n[Open in Deep Research](#research-{_rsid})\n"
            state.events.append('data: ' + json.dumps({"delta": _anchor}) + '\n\n')

        tool_event = {
            "round": state.round_num,
            "tool": block.tool_type,
            "command": cmd_display,
            "output": output_text,
            "exit_code": result.get("exit_code"),
        }
        if result.get("image_url"):
            for ik in ("image_url", "image_prompt", "image_model", "image_size", "image_quality"):
                if result.get(ik):
                    tool_event[ik] = result[ik]
        if result.get("doc_id"):
            tool_event["doc_id"] = result["doc_id"]
            tool_event["doc_title"] = result.get("title", "")
        state.tool_events.append(tool_event)
        if block.tool_type in _VERIFIER_EFFECTFUL_TOOLS:
            state.effectful_used = True

        state.total_tool_calls += 1
        formatted = format_tool_result(r["desc"], result)
        tool_results.append(formatted)
        tool_result_texts.append(formatted)

    rs.tool_results = tool_results
    rs.tool_result_texts = tool_result_texts

    _append_tool_results(
        state.messages, rs.response, rs.native_tool_calls,
        tool_results, tool_result_texts, True, state.round_num,
        round_reasoning=rs.reasoning,
    )

    state.events.append(
        f'data: {json.dumps({"type": "agent_step", "round": state.round_num + 1})}\n\n'
    )
    state.full_response += "\n\n"

    if state.session_id:
        try:
            from core.session_db import save_snapshot as _save_snap
            _save_snap(state)
        except Exception as _e:
            logger.debug("[session-db] snapshot save skipped: %s", _e)

    state.phase = AgentPhase.THINKING
    return state


# ── Human-in-the-loop ────────────────────────────────────────────

_HITL_EFFECTFUL_TOOLS = {
    "bash", "python", "create_document", "update_document",
    "edit_document", "write_file", "manage_tasks", "manage_notes",
    "manage_mcp", "send_email",
}


async def pause_node(state: AgentState) -> AgentState:
    """Check for effectful tools and pause for human approval if enabled."""
    rs = state.round_state
    if not rs or not rs.tool_blocks:
        state.phase = AgentPhase.TOOL_CALLING
        return state

    if not state.pause_before_effectful:
        state.phase = AgentPhase.TOOL_CALLING
        return state

    paused = []
    for block in rs.tool_blocks:
        if block.tool_type in _HITL_EFFECTFUL_TOOLS:
            paused.append({
                "tool": block.tool_type,
                "description": block.content.strip()[:200],
                "index": len(paused),
            })

    if not paused:
        state.phase = AgentPhase.TOOL_CALLING
        return state

    state.paused_tool_data = paused

    try:
        from core.persistence.store import checkpoint_store
        checkpoint_store.save_agent_state(state)
    except Exception as e:
        logger.warning("[graph] Failed to save agent state for HITL resume: %s", e)

    state.events.append(
        'data: ' + json.dumps({
            "type": "human_review",
            "run_id": state.run_id,
            "round": state.round_num,
            "tools": paused,
            "instruction": "Approve or reject the proposed tool executions.",
        }) + '\n\n'
    )

    state.phase = AgentPhase.PAUSED
    return state


async def resume_node(state: AgentState) -> AgentState:
    """Process human-in-the-loop resume action from an external API call."""
    if state.resume_action == "approve":
        state.resume_action = ""
        state.resume_feedback = ""
        state.paused_tool_data = None
        state.events.append(
            'data: ' + json.dumps({
                "type": "resume_approved",
                "round": state.round_num,
            }) + '\n\n'
        )
        state.phase = AgentPhase.TOOL_CALLING
        return state

    if state.resume_action == "reject":
        feedback = state.resume_feedback or "The proposed tools were rejected by the user."
        state.messages.append({
            "role": "system",
            "content": (
                f"The user rejected the tool call and provided this feedback: "
                f"{feedback}\n\nDo NOT repeat the same tool calls. "
                f"Adjust your approach based on the feedback."
            ),
        })
        state.resume_action = ""
        state.resume_feedback = ""
        state.paused_tool_data = None
        state.events.append(
            'data: ' + json.dumps({
                "type": "resume_rejected",
                "round": state.round_num,
                "feedback": feedback,
            }) + '\n\n'
        )
        state.phase = AgentPhase.THINKING
        return state

    state.phase = AgentPhase.PAUSED
    return state


# ── Parallel sub-agents ──────────────────────────────────────────


async def _run_sub_agent(
    endpoint_url: str, model: str, headers: dict,
    messages: list[dict], task: str, tool_names: list[str] | None,
    session_id: str | None, disabled_tools_set: set,
    owner: str | None, idx: int,
) -> dict:
    """Run one sub-agent: single LLM call + tool execution."""
    try:
        sub_messages = list(messages) + [{"role": "user", "content": task}]

        from core.agent_helpers import _resolve_tool_blocks
        from core.agent_tools import FUNCTION_TOOL_SCHEMAS as _FTS
        from core.llm_core import stream_llm_with_fallback

        tool_schemas = [
            s for s in _FTS
            if s.get("function", {}).get("name") in (tool_names or [])
        ] if tool_names else []

        response = ""
        async for chunk in stream_llm_with_fallback(
            [(endpoint_url, model, headers)],
            sub_messages, temperature=0.3, max_tokens=2048,
            tools=tool_schemas or None, timeout=120,
        ):
            if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                try:
                    data = json.loads(chunk[6:])
                    if "delta" in data:
                        response += data["delta"]
                except json.JSONDecodeError:
                    pass

        blocks, _ = _resolve_tool_blocks(response, [], idx)

        results = []
        for block in blocks:
            if session_id:
                desc, result = await execute_tool_block(
                    block, session_id=session_id,
                    disabled_tools=disabled_tools_set,
                    owner=owner,
                )
            else:
                desc, result = await execute_tool_block(
                    block, owner=owner,
                    disabled_tools=disabled_tools_set,
                )
            results.append({"tool": block.tool_type, "desc": desc, "output": result})

        return {
            "index": idx,
            "task": task,
            "response": response,
            "results": results,
            "error": None,
        }
    except Exception as e:
        logger.warning("[graph] Sub-agent %d failed: %s", idx, e)
        return {"index": idx, "task": task, "error": str(e), "results": []}


async def parallel_sub_agents_node(state: AgentState) -> AgentState:
    """Fan-out: execute multiple sub-agent tasks concurrently, fan-in: collect results."""
    configs = state.parallel_sub_agents
    if not configs:
        state.phase = AgentPhase.THINKING
        return state

    state.events.append(
        'data: ' + json.dumps({
            "type": "parallel_start",
            "count": len(configs),
            "round": state.round_num,
        }) + '\n\n'
    )

    tasks = [
        _run_sub_agent(
            state.endpoint_url, state.model, state.headers or {},
            state.messages, cfg.get("task", ""), cfg.get("tools"),
            state.session_id, state.disabled_tools_set,
            state.owner, i,
        )
        for i, cfg in enumerate(configs)
    ]

    results = await asyncio.gather(*tasks)
    state.parallel_results = results

    for r in results:
        if r.get("error"):
            state.events.append(
                'data: ' + json.dumps({
                    "type": "parallel_error",
                    "index": r["index"],
                    "error": r["error"],
                }) + '\n\n'
            )

    state.events.append(
        'data: ' + json.dumps({
            "type": "parallel_complete",
            "count": len(results),
            "errors": sum(1 for r in results if r.get("error")),
        }) + '\n\n'
    )

    state.phase = AgentPhase.THINKING
    return state


async def verify_node(state: AgentState) -> AgentState:
    rs = state.round_state
    if not rs:
        state.phase = AgentPhase.THINKING
        return state

    state.verifier_rounds += 1
    _vfail = await _run_verifier_subagent(
        state.verifier_instruction,
        _build_actions_snapshot(state.tool_events),
        endpoint_url=state.endpoint_url,
        model=state.model,
        headers=state.headers,
    )
    if _vfail:
        logger.info(f"[agent] verifier flagged {len(_vfail)} issue(s) on round {state.round_num}: {_vfail}")
        _note = "\n\n_Double-checked the work and found something to fix._\n\n"
        state.events.append(f'data: {json.dumps({"delta": _note})}\n\n')
        state.full_response += _note
        state.messages.append({
            "role": "system",
            "content": (
                "An independent verifier reviewed your work against the "
                "original request and found issues that must be fixed before "
                "this is actually done:\n- " + "\n- ".join(_vfail) +
                "\n\nFix these now using tools, then finish."
            ),
        })
        state.reset_for_verifier()
        state.phase = AgentPhase.THINKING
        return state

    state.phase = AgentPhase.FINISHED
    return state


async def force_answer_node(state: AgentState) -> AgentState:
    from core.llm_core import llm_call_async as _llm_call
    _synth = ""
    try:
        _synth_messages = list(state.messages) + [{
            "role": "user",
            "content": (
                "Using ONLY the information already gathered above, write "
                "the final answer for the user now. Do NOT call any tools."
            ),
        }]
        _raw = await _llm_call(
            url=state.endpoint_url, model=state.model,
            messages=_synth_messages,
            headers=state.headers, temperature=0.3,
            max_tokens=state.max_tokens, timeout=60,
        )
        _synth = THINK_RE.sub("", strip_tool_blocks(_raw or "")).strip()
    except Exception as _e:
        logger.warning(f"[agent] grace synthesis failed: {_e}")
    if _synth:
        state.events.append(f'data: {json.dumps({"delta": _synth})}\n\n')
        state.full_response += _synth
    else:
        _fb = ("I gathered some search results but couldn't pull a clean "
               "answer together. Want me to try a more specific question, "
               "or summarize what I did find?")
        state.events.append(f'data: {json.dumps({"delta": _fb})}\n\n')
        state.full_response += _fb
    state.phase = AgentPhase.FINISHED
    return state


async def finish_node(state: AgentState) -> AgentState:
    rs = state.round_state
    round_reasoning = rs.reasoning if rs else ""

    state.full_response, _fallback_chunk = _empty_response_fallback(
        state.full_response, round_reasoning, state.tool_events
    )
    if _fallback_chunk:
        state.events.append(_fallback_chunk)

    total_duration = time.time() - state.total_start
    metrics = _compute_final_metrics(
        state.messages, state.full_response, total_duration,
        state.time_to_first_token,
        state.context_length, state.real_input_tokens,
        state.real_output_tokens,
        state.has_real_usage, state.tool_events, state.round_texts,
        model=state.model,
        last_round_input_tokens=state.last_round_input_tokens,
        prep_timings=state.prep_timings,
        backend_gen_tps=state.backend_gen_tps,
        backend_prefill_tps=state.backend_prefill_tps,
    )
    state.events.append(
        f"data: {json.dumps({'type': 'metrics', 'data': metrics})}\n\n"
    )

    if not state._is_teacher_run:
        try:
            from core.teacher_escalation import run_teacher_inline
            async for evt in run_teacher_inline(
                student_endpoint_url=state.endpoint_url,
                student_messages=state.messages,
                student_tool_events=state.tool_events,
                student_reply=state.full_response,
                owner=state.owner,
            ):
                state.events.append(evt)
        except Exception as _esc_err:
            logger.warning(f"teacher escalation hook failed: {_esc_err}", exc_info=True)

    state.phase = AgentPhase.FINISHED
    return state
