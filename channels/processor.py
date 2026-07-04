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

import logging

logger = logging.getLogger(__name__)


async def process_message(
    text: str,
    source: str,
    channel_id: str,
    user_id: str,
    user_name: str,
) -> str:
    from brain.epistemic_tagger import epistemic_tagger
    from core.llm_router import get_router
    from core.model_router import get_ollama_url, model_for_role, route_request

    try:
        model, tier, processed_query = route_request(text)

        non_chat_intents = ("pc_control", "open_url", "play_media", "reminder", "weather", "news", "web_search", "search")
        current_intent = "chat"

        try:
            from core.intent_router import extract_intent
            from core.main import execute_action
            intent_data = await extract_intent(processed_query)
            action_result = await execute_action(intent_data, message=text)
            current_intent = intent_data.get("intent", "chat")
        except Exception as e:
            logger.warning("[channels.processor] intent extraction failed: %s", e)
            intent_data = {"intent": "chat"}
            action_result = {"executed": False}

        provenance = {"source": source, "confidence": 0.5, "url": None}

        if current_intent in non_chat_intents and action_result.get("executed") and not action_result.get("error"):
            response_text = action_result.get("action", f"{current_intent} completed")
        else:
            try:
                vision_keywords = ["screen", "screenshot", "see", "look", "what is on", "what's on", "what do you see", "what am i looking"]
                is_vision = any(kw in text.lower() for kw in vision_keywords)
                if is_vision or current_intent == "vision":
                    try:
                        from core.vision_agent import VisionAgent
                        agent = VisionAgent()
                        state = await agent._capture()
                        screen_desc = await agent._describe(state)
                        processed_query += f"\n[SCREEN CAPTURE: {screen_desc}]"
                    except Exception as e:
                        logger.warning("[Channel] Vision capture failed: %s", e)

                model_group = "cloud" if model == "cloud" else current_intent
                try:
                    from core.llm_router import complete_vision
                    if is_vision:
                        vision_result = await complete_vision([
                            {"role": "system", "content": "You are JARVIS, your AI assistant. Be concise."},
                            {"role": "user", "content": processed_query}
                        ], timeout=60)
                        resp_text = vision_result.unwrap_or("")
                        response_text = epistemic_tagger.tag_response(resp_text, provenance)
                    else:
                        resp = await get_router().acompletion(
                            model=model_group,
                            messages=[{"role": "system", "content": "You are JARVIS, your AI assistant. Be concise."},
                                      {"role": "user", "content": processed_query}],
                            timeout=60,
                        )
                        response_text = epistemic_tagger.tag_response(
                            resp.choices[0].message.content, provenance
                        )
                except Exception as e:
                    logger.warning("[Channel] LiteLLM fallback to Ollama: %s", e)
                    model_obj = model_for_role(current_intent)
                    direct_url = get_ollama_url(model_obj)
                    import httpx
                    async with httpx.AsyncClient(timeout=60) as client:
                        r = await client.post(f"{direct_url}/api/chat", json={
                            "model": model_obj,
                            "messages": [{"role": "system", "content": "You are JARVIS, your AI assistant. Be concise."},
                                         {"role": "user", "content": processed_query}],
                            "stream": False,
                            "options": {"num_predict": 1024, "temperature": 0.7, "num_gpu": 99},
                        })
                        resp_text = r.json().get("message", {}).get("content", "")
                    response_text = epistemic_tagger.tag_response(resp_text, provenance)
            except Exception as e:
                logger.exception("[Channel] All LLM fallbacks failed: %s", e)
                response_text = "I had a temporary issue processing that request."

        logger.info("[Channel] %s|%s|%s -> %.80s", source, channel_id, user_name, response_text)

        # Phase 3: Emit hook
        try:
            import asyncio

            from brain.events import PluginEventBus
            asyncio.create_task(PluginEventBus.instance().emit(
                "on_channel_message",
                text=text,
                source=source,
                channel_id=channel_id,
                user_id=user_id,
                user_name=user_name,
                response=response_text
            ))
        except Exception as hook_exc:
            logger.debug("on_channel_message hook failed: %s", hook_exc)

        # Phase 6: MCP Bridge notification
        try:
            from mcp.server import mcp_server
            if mcp_server.is_running:
                mcp_server.enqueue_event("message", {
                    "session_key": channel_id,
                    "role": "user",
                    "text": text,
                    "source": source,
                    "user_id": user_id,
                    "user_name": user_name
                })
                mcp_server.enqueue_event("message", {
                    "session_key": channel_id,
                    "role": "assistant",
                    "text": response_text,
                    "source": "jarvis"
                })
        except Exception as bridge_exc:
            logger.debug("MCP Server event enqueuing failed: %s", bridge_exc)

        return response_text

    except Exception as e:
        logger.exception("[Channel] process_message failed: %s", e)
        return "I encountered an error processing your message."
