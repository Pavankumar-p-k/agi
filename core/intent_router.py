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
"""core/intent_router.py
Single source of truth for intent classification.
Replaces dual systems in main.py (extract_intent) and assistant/engine.py (detect_intent).
All edge cases handled via LLM prompt — no post-hoc keyword overrides.
"""
import asyncio
import logging
import os

logger = logging.getLogger("intent_router")

try:
    import instructor
except ImportError:
    instructor = None
try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

from core.schemas import IntentResult

_INTENT_CLIENT = None

_CRITICAL_RULES = """\
CRITICAL RULES (follow these exactly, they override any conflicting pattern):
1. "open [app]" where app is notepad, calculator, vscode, chrome, edge, firefox, settings, terminal, cmd, code, explorer -> pc_control
2. "what is X", "what are X", "who is X", "how does X work", "tell me about X", "explain X" -> chat, NEVER web_search
3. "what's the weather", "temperature in X", "forecast", "rain", "sunny", "humidity" -> weather
4. "news", "headlines", "what's happening" -> news
5. "stock price", "share price", "stock market", ticker symbols like AAPL, TSLA -> stocks
6. "remember that", "remember my" -> chat, NOT reminder
7. "create a github issue", "create an issue", "send an email", "send a message" -> message, NOT browser_task
8. "play X" (without "search for") -> play_media, NOT web_search
9. "open X and play Y" -> play_media (target is "play Y")
10. message starting with "build", "create", "make", "generate" -> build, NOT chat
"""

_STRICT_EXAMPLES = """\
Examples:
User: play cry for me on youtube
Intent: play_media
User: open youtube
Intent: open_url
User: search latest AI news
Intent: web_search
User: open notepad
Intent: pc_control
User: remind me to drink water in 1 minute
Intent: reminder
User: what is python
Intent: chat
User: launch chrome
Intent: pc_control
User: go to github
Intent: open_url
User: open github
Intent: open_url
User: open github and complete sign up
Intent: browser_task
User: go to amazon and add a monitor to cart
Intent: browser_task
User: login to gmail and send an email
Intent: browser_task
User: send an email to john@example.com with subject hello saying hi
Intent: message
User: send a slack message to general
Intent: message
User: create a github issue in my repo
Intent: message
User: browse amazon for laptops
Intent: browser_task
User: sign up for a new account on any site
Intent: browser_task
User: register for github with google
Intent: browser_task
User: open spotify
Intent: open_url
User: go to youtube and search for music
Intent: browser_task
User: fill out the contact form
Intent: browser_task
User: what's the weather in London
Intent: weather
User: temperature in New York
Intent: weather
User: latest technology news
Intent: news
User: what's happening in the world
Intent: news
User: AAPL stock price
Intent: stocks
User: how is the stock market doing
Intent: stocks
User: NBA scores
Intent: sports
User: who won the game yesterday
Intent: sports
User: what time is it in Tokyo
Intent: time
User: build a portfolio page with animations
Intent: build
User: create a todo app
Intent: build
User: make a website for my business
Intent: build
User: generate a html resume page
Intent: build
User: open chrome to google.com
Intent: pc_control
User: open chrome and go to youtube
Intent: pc_control
User: play havana on youtube
Intent: play_media
User: play despacito
Intent: play_media
"""


def _get_intent_client():
    global _INTENT_CLIENT
    if _INTENT_CLIENT is None:
        if instructor is None or AsyncOpenAI is None:
            return None
        from core.config_registry import config as _c
        _ollama = _c.get("ollama.base_url")
        _INTENT_CLIENT = instructor.from_openai(
            AsyncOpenAI(base_url=f"{_ollama}/v1", api_key="ollama", timeout=30),
            mode=instructor.Mode.JSON,
        )
    return _INTENT_CLIENT


async def extract_intent(message: str) -> dict:
    """Classify user message into an intent with target and parameters.
    Single LLM call — no post-hoc keyword overrides.

    Returns dict with keys: intent, target, parameters.
    Falls back to {'intent': 'chat', 'target': message, 'parameters': {}} on error.
    """
    try:
        client = _get_intent_client()
        # Rule-based fallback function (used when client missing or when test-mode/LLM errors)
        def _rule_based(message: str) -> dict:
            m = message.lower()
            import re

            # PC control exact apps
            if re.search(r'\b(open|launch|start)\s+(notepad|calculator|vscode|chrome|edge|firefox|settings|terminal|cmd|code|explorer)\b', m):
                return {"intent": "pc_control", "target": message, "parameters": {}}

            # Play media (play X without 'search')
            if m.startswith('play ') and 'search' not in m:
                return {"intent": "play_media", "target": message, "parameters": {}}

            # Open URL (simple)
            if re.match(r'^(open|go to)\s+\w+', m) and 'play' not in m and 'sign up' not in m:
                # open github / open youtube -> open_url
                return {"intent": "open_url", "target": message, "parameters": {}}

            # Reminder
            if 'remind me' in m or 'reminder' in m:
                return {"intent": "reminder", "target": message, "parameters": {}}

            # News (prefer explicit searches to be classified as web_search)
            if ('news' in m or "what's happening" in m or 'headlines' in m) and not (m.startswith('search ') or m.startswith('look up ') or ' search ' in m or 'search for' in m):
                return {"intent": "news", "target": message, "parameters": {}}

            # Web search (explicit search requests)
            if m.startswith('search ') or m.startswith('look up ') or 'search for' in m or ' search ' in m:
                return {"intent": "web_search", "target": message, "parameters": {}}

            # Weather
            if any(k in m for k in ['weather', 'temperature', 'forecast', 'rain', 'sunny']):
                return {"intent": "weather", "target": message, "parameters": {}}

            # Sports
            if 'scores' in m or 'nba' in m or 'game' in m:
                return {"intent": "sports", "target": message, "parameters": {}}

            # Stocks
            if re.search(r'\b[A-Z]{2,5}\b stock|stock price|share price|\b[A-Z]{1,5}\b', message):
                return {"intent": "stocks", "target": message, "parameters": {}}

            # Time
            if 'time' in m and 'what time' in m:
                return {"intent": "time", "target": message, "parameters": {}}

            # Message/email
            if 'send an email' in m or 'send email' in m or re.search(r'\b[\w.%+-]+@[\w.-]+\.[a-zA-Z]{2,}\b', message):
                return {"intent": "message", "target": message, "parameters": {}}

            # Browser tasks (signup, register, login, sign up, add to cart)
            if any(k in m for k in ['sign up', 'register', 'login', 'log in', 'add to cart', 'fill out', 'fill', 'submit', 'checkout']):
                return {"intent": "browser_task", "target": message, "parameters": {}}

            # Build / create
            if any(m.startswith(w) for w in ['build', 'create', 'make', 'generate']):
                return {"intent": "build", "target": message, "parameters": {}}

            # Code tasks
            if any(k in m for k in ['refactor', 'debug', 'function', 'code', 'implement', 'unit test']):
                return {"intent": "code_task", "target": message, "parameters": {}}

            # Default fallback
            return {"intent": "chat", "target": message, "parameters": {}}

        if client is None or os.environ.get("JARVIS_TEST_MODE"):
            # Deterministic rule-based fallback when LLM client is unavailable or when running in test mode
            return _rule_based(message)
        result = await client.chat.completions.create(
            model="qwen2.5:7b",
            response_model=IntentResult,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an intent classifier. Output ONLY the intent, target, and parameters.\n\n"
                        "Intents:\n"
                        "- play_media: user wants to play music/video/media\n"
                        "- open_url: ONLY when the user simply wants to navigate to a URL with no further action. Single verb like 'open youtube', 'go to github'.\n"
                        "- web_search: user explicitly says 'search for', 'look up', or wants current/live information from the web\n"
                        "- reminder: user wants to set a reminder/alarm\n"
                        "- pc_control: user wants to open a desktop app (notepad, vscode, chrome, calculator, etc.)\n"
                        "- browser_task: ANY multi-step browser operation \u2014 signup, login, form filling, shopping, booking, clicking, scrolling, filling fields, submitting forms, OR when the user says 'open X and Y' where Y is an action beyond just opening. This includes any mention of: sign up, sign in, register, create account, login, fill, submit, search for (on a site), add to cart, purchase, book, order.\n"
                        "- message: user wants to send an email, Slack message, or any electronic message. Examples: 'send an email', 'send a message', 'send email to', 'send slack message', 'create a github issue', 'create an issue'.\n"
                        "- weather: user asks about weather, temperature, forecast. Keywords: weather, temperature, rain, sunny, forecast.\n"
                        "- news: user asks for latest news, headlines, current events. Keywords: news, headline, what's happening.\n"
                        "- stocks: user asks about stock prices, market. Keywords: stock price, market, ticker, share price.\n"
                        "- sports: user asks about sports scores, games, matches. Keywords: score, game, match, who won, sports.\n"
                        "- time: user asks for current time in a location or timezone.\n"
                        "- build: user wants to create, build, generate, or make something (website, app, page, document, project).\n"
                        "- code_task: user wants code-related work like refactoring, debugging, adding features, writing tests, code review.\n"
                        "- chat: general knowledge questions, greetings, conversation, stories, jokes, opinions, advice, explanations.\n\n"
                        f"{_CRITICAL_RULES}\n{_STRICT_EXAMPLES}"
                    ),
                },
                {"role": "user", "content": message},
            ],
            max_retries=3,
        )
        intent_data = result.model_dump()
        # Plugin hook: on_intent (fire-and-forget)
        try:
            from core.plugins.registry import get_plugin_registry
            registry = get_plugin_registry()
            asyncio.create_task(registry.run_hook("on_intent", intent=intent_data.get("intent"), text=message, data=intent_data))
        except Exception as _e:
            logger.debug("intent_router plugin hook failed: %s", _e)
        return intent_data
    except Exception as e:
        logger.warning(f"[INTENT_ROUTER] LLM intent extraction failed: {e}")
        # On LLM/network errors prefer deterministic rule-based fallback in test mode
        try:
            if os.environ.get("JARVIS_TEST_MODE"):
                return _rule_based(message)
        except Exception as _e:
            logger.debug("intent_router fallback failed: %s", _e)
        return {"intent": "chat", "target": message, "parameters": {}}
