"""Extracted chat handler with 3-pass reasoning, platform detection, and multi-format output."""

from __future__ import annotations

import json
import re

from brain.epistemic_tagger import epistemic_tagger
from brain.UnifiedBrain import unified_brain
from core.format_classifier import FormatClassifier
from core.prompts import get_prompt
from core.schemas import COMPLEX_TASK_TYPES, ChatRequest, MultiFormatResponse
from core.skill_loader import match_skill, run_skill

format_classifier = FormatClassifier()


def get_system_prompt(req: ChatRequest, endpoint: str = "/api/chat") -> str:
    platform = getattr(req, "platform", "") or ""
    if endpoint in ("/voice", "/api/stt") or platform == "voice":
        return get_prompt("voice")
    if platform == "mobile":
        return get_prompt("mobile")
    return get_prompt("chat")


async def build_response(answer: str, fmt: str,
                          query: str) -> MultiFormatResponse:
    if fmt == "artifact":
        artifact_prompt = (
            f"Build a self-contained HTML/React artifact for: {query}\n"
            f"Context: {answer}\n"
            f"Output only the code, no explanation."
        )
        code = await unified_brain.reason(artifact_prompt, {})
        return MultiFormatResponse(
            prose=answer,
            artifact_code=code.answer,
            artifact_type="html",
            format_used="artifact"
        )
    elif fmt == "json":
        match = re.search(r'\{.*\}|\[.*\]', answer, re.DOTALL)
        json_data = None
        if match:
            try:
                json_data = json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return MultiFormatResponse(prose=answer, json_data=json_data, format_used="json")
    elif fmt == "scene":
        try:
            from tools.scene_generator import scene_generator
            scene_result = await scene_generator.generate(
                description   = query,
                brain         = unified_brain,
                output_format = "auto"
            )
            if scene_result.success and scene_result.artifact_code:
                return MultiFormatResponse(
                    prose         = answer,
                    artifact_code = scene_result.artifact_code,
                    artifact_type = "html",
                    format_used   = "scene"
                )
            elif scene_result.success and scene_result.render_path:
                return MultiFormatResponse(
                    prose       = f"{answer}\n\nRendered to: {scene_result.render_path}",
                    format_used = "scene"
                )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Scene generation failed: %s", e)
    return MultiFormatResponse(prose=answer, format_used=fmt)


async def chat_handler(req: ChatRequest, endpoint: str = "/api/chat") -> dict:
    """Process a chat request through reason() → optional three_pass() → epistemic tags.

    For responses > 200 chars or complex task types, run three_pass() critique loop.
    Uses FormatClassifier to detect desired output format from the query.
    Uses get_system_prompt() to pick platform-appropriate system prompt.
    Returns dict matching the standard API response format.
    """
    system_prompt = get_system_prompt(req, endpoint)

    # Check skills first — instant response without hitting the LLM
    handler = match_skill(req.message)
    if handler:
        result_text = await run_skill(handler, req.message)
        return {
            "response": result_text,
            "intent": {"intent": "skill"},
            "action": {"executed": True, "skill": True},
            "model": "skill",
            "privacy_tier": "LOCAL",
            "epistemic_tags": ["VERIFIED"],
            "format_used": "prose",
            "multi_format": {"prose": result_text, "json_data": None, "html": None, "artifact_type": None, "artifact_code": None},
        }

    fmt = await format_classifier.classify(req.message)

    raw = await unified_brain.reason(
        req.message,
        {"context": req.context or "", "system_prompt": system_prompt} if req.context
        else {"system_prompt": system_prompt},
    )

    task_type = getattr(req, "task_type", None)
    if len(raw.answer) > 200 or (task_type and task_type in COMPLEX_TASK_TYPES):
        final = await unified_brain.three_pass(
            req.message,
            {"context": req.context or "", "system_prompt": system_prompt} if req.context
            else {"system_prompt": system_prompt},
        )
    else:
        final = raw.answer

    provenance = raw.provenance or {"source": "inference", "confidence": 0.5, "url": None}
    tagged = epistemic_tagger.tag_response(final, provenance)

    mfr = await build_response(tagged, fmt, req.message)

    tag_label = provenance.get("source", "inference").upper()
    if tag_label == "WEB_SEARCH":
        tag_label = "RETRIEVED"
    elif tag_label in ("MEMORY", "TOOL_RESULT"):
        tag_label = "VERIFIED"
    elif tag_label == "INFERENCE":
        tag_label = "INFERRED"
    else:
        tag_label = "ASSUMED"

    return {
        "response": tagged,
        "intent": {"intent": "chat"},
        "action": {"executed": True},
        "model": "reasoning",
        "privacy_tier": "LOCAL",
        "epistemic_tags": [tag_label],
        "format_used": fmt,
        "multi_format": {
            "prose": mfr.prose,
            "json_data": mfr.json_data,
            "html": mfr.html,
            "artifact_type": mfr.artifact_type,
            "artifact_code": mfr.artifact_code,
        },
    }
