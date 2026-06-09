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
import logging
import os
import time

from core.config_schema import AuthProfile, jarvis_config
from core.errors import AuthFailed, LLMError, ProviderError, RateLimited, Timeout
from core.result import Err, Ok, Result

logger = logging.getLogger("jarvis.core.llm_failover")

class ProfileManager:
    """Manages LLM AuthProfiles, priorities, discovery, and cooldown states."""

    def __init__(self):
        self.config = jarvis_config.failover
        self._profiles: list[AuthProfile] = []
        self._cooldowns: dict[str, float] = {}  # profile_name -> wakeup_time
        self._failure_counts: dict[str, int] = {}  # profile_name -> sequential failure count
        self._lock = asyncio.Lock()
        self._vault_loaded = False
        self._refresh_profiles()

    _KNOWN_LLM_PROVIDERS = frozenset({
        "openai", "anthropic", "google", "gemini", "cohere", "ai21", "aleph_alpha",
        "replicate", "huggingface", "together", "mistral", "perplexity", "deepseek",
        "groq", "xai", "sambanova", "cerebras", "fireworks", "llamaapi",
        "voyage", "jina", "cohere", "ollama", "azure", "bedrock", "vertexai",
    })

    def _discover_profiles(self) -> list[AuthProfile]:
        """Discover profiles from config and environment variables."""
        profiles = list(jarvis_config.failover.profiles)
        seen = {p.name for p in profiles}

        # Tier 2: Environment variables (known LLM providers only)
        for key, val in os.environ.items():
            if key.endswith("_API_KEY") and not key.startswith("JARVIS_"):
                name = key.removesuffix("_API_KEY").lower()
                if name not in seen and val and name in self._KNOWN_LLM_PROVIDERS:
                    profiles.append(AuthProfile(name=name, api_key=val, provider=name))
                    seen.add(name)
        return profiles

    def _refresh_profiles(self):
        """Update the internal profile list (non-vault sources)."""
        self._profiles = sorted(
            self._discover_profiles(), key=lambda p: p.priority, reverse=True
        )

    async def _load_vault_profiles(self):
        """Lazy-load profiles from the APIKeyVault (known LLM providers only)."""
        if self._vault_loaded:
            return

        try:
            from core.api_key_vault import vault
            seen = {p.name for p in self._profiles}
            for service, key, pri in vault.get_profiles():
                provider = service.split("_")[0]
                if provider not in self._KNOWN_LLM_PROVIDERS:
                    continue
                if service not in seen:
                    self._profiles.append(AuthProfile(
                        name=service, api_key=key, provider=provider, priority=pri
                    ))
                    seen.add(service)

            self._profiles.sort(key=lambda p: p.priority, reverse=True)
            self._vault_loaded = True
        except Exception as e:
            logger.warning("[Failover] Failed to load vault profiles: %s", e)

    async def get_next_profile(self, provider: str | None = None) -> AuthProfile | None:
        """Get the highest priority profile that isn't on cooldown."""
        if not self._vault_loaded:
            await self._load_vault_profiles()

        now = time.time()
        async with self._lock:
            for profile in self._profiles:
                if provider and profile.provider != provider:
                    continue

                wakeup = self._cooldowns.get(profile.name, 0)
                if now >= wakeup:
                    return profile
            return None

    def _get_profile(self, name: str) -> AuthProfile | None:
        return next((p for p in self._profiles if p.name == name), None)

    async def set_cooldown(self, name: str, error_type: type | None = None):
        """Put a profile on cooldown with exponential backoff."""
        async with self._lock:
            hits = self._failure_counts.get(name, 0) + 1
            self._failure_counts[name] = hits

            base = jarvis_config.failover.cooldown_backoff_base
            # Exponential: 60s, 120s, 240s, 480s...
            duration = base * (2 ** (hits - 1))

            # Auth errors get a heavy cooldown
            if error_type == AuthFailed:
                duration = max(duration, 3600)

            duration = min(duration, 3600)  # Cap at 1 hour
            self._cooldowns[name] = time.time() + duration
            logger.warning("[Failover] Profile '%s' cooldowned for %ds (failures: %d)", name, duration, hits)

    def record_success(self, name: str):
        """Reset failure counts on success."""
        self._failure_counts[name] = 0
        self._cooldowns.pop(name, None)

class CooldownProbe:
    """Background task that probes cooldowned profiles for recovery."""

    def __init__(self, manager: ProfileManager, interval: int = 60):
        self._pm = manager
        self._interval = interval
        self._task: asyncio.Task | None = None

    async def start(self):
        if not self._task:
            self._task = asyncio.create_task(self._loop())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self):
        logger.info("[Failover] Cooldown probe loop active")
        while True:
            await asyncio.sleep(self._interval)
            now = time.time()
            # Copy items to avoid modification during iteration
            for name, wakeup in list(self._pm._cooldowns.items()):
                if now >= wakeup:
                    profile = self._pm._get_profile(name)
                    if profile and await self._probe(profile):
                        self._pm.record_success(name)
                        logger.info("[Failover] Profile '%s' recovered — removed from cooldown", name)

    async def _probe(self, profile: AuthProfile) -> bool:
        """Minimal completion call to check if endpoint is healthy."""
        try:
            from litellm import Router
            # Use a fast, cheap model if possible
            model = f"{profile.provider}/gpt-4o-mini" if profile.provider == "openai" else f"{profile.provider}/claude-3-haiku-20240307"

            router = Router(model_list=[{
                "model_name": "probe",
                "litellm_params": {
                    "model": model,
                    "api_key": profile.api_key,
                    "max_tokens": 1,
                    "timeout": 5,
                }
            }])

            resp = await router.acompletion(
                model="probe",
                messages=[{"role": "user", "content": "ping"}],
                timeout=5
            )
            return bool(resp.choices)
        except Exception as e:
            logger.debug("[Failover] Probe for %s failed: %s", profile.name, e)
            return False

class FailoverRouter:
    """Orchestrates LLM completions with failover across discovered profiles."""

    def __init__(self, profile_manager: ProfileManager):
        self.pm = profile_manager

    async def complete(self, model_group: str, messages: list[dict], **kwargs) -> Result[str, LLMError]:
        """Perform completion with retry and failover logic."""
        from core.llm_router import get_router

        tried_profiles: set[str] = set()
        max_retries = jarvis_config.failover.max_retries_per_profile

        while True:
            profile = await self.pm.get_next_profile()

            # If no healthy profiles, fallback to default litellm routing
            if not profile or profile.name in tried_profiles:
                if tried_profiles:
                    logger.warning("[Failover] No healthy untried profiles left, calling router directly")
                else:
                    logger.debug("[Failover] No configured profiles, calling router directly")
                from core.llm_router import get_router
                try:
                    response = await get_router().acompletion(
                        model=model_group,
                        messages=messages,
                        **{k: v for k, v in kwargs.items() if k != 'model'}
                    )
                    return Ok(response.choices[0].message.content)
                except Exception as e:
                    return Err(LLMError(str(e)))

            model = self._resolve_model(model_group, profile.provider)

            try:
                logger.info("[Failover] Trying %s with profile '%s' (model: %s)", model_group, profile.name, model)

                response = await get_router().acompletion(
                    model=model,
                    messages=messages,
                    api_key=profile.api_key,
                    **{k: v for k, v in kwargs.items() if k != 'model'}
                )

                self.pm.record_success(profile.name)
                return Ok(response.choices[0].message.content)

            except Exception as e:
                err_cls = self._classify_error(e)
                logger.warning("[Failover] Profile '%s' failed with %s: %s",
                               profile.name, err_cls.__name__, e)

                tried_profiles.add(profile.name)

                if err_cls in (AuthFailed, RateLimited):
                    # Hard failure: cooldown immediately
                    await self.pm.set_cooldown(profile.name, err_cls)
                else:
                    # Transient/Generic: maybe retry once if it's the first time
                    # But for simplicity in failover, we usually want to move to next profile fast
                    await self.pm.set_cooldown(profile.name, err_cls)

                # Continue loop to try next profile

    def _resolve_model(self, model_group: str, provider: str) -> str:
        """Map model_group to a provider-specific string LiteLLM understands."""
        fallbacks = {
            "chat": {
                "openai": "openai/gpt-4o",
                "anthropic": "anthropic/claude-3-5-sonnet-20240620",
                "ollama": "ollama/llama3.1:8b"
            },
            "code": {
                "openai": "openai/gpt-4o",
                "anthropic": "anthropic/claude-3-5-sonnet-20240620"
            },
            "analysis": {
                "openai": "openai/gpt-4o",
                "anthropic": "anthropic/claude-3-5-sonnet-20240620"
            },
            "reasoning": {
                "openai": "openai/o1",
                "anthropic": "anthropic/claude-3-5-sonnet-20240620",
                "deepseek": "deepseek/deepseek-reasoner"
            },
        }

        target = fallbacks.get(model_group, {}).get(provider)
        if target:
            return target

        # Fallback: just prepend provider/
        return f"{provider}/{model_group}"

    @staticmethod
    def _classify_error(e: Exception) -> type[LLMError]:
        msg = str(e).lower()
        if "429" in msg or "rate limit" in msg or "too many requests" in msg:
            return RateLimited
        if "401" in msg or "403" in msg or "auth" in msg or "invalid api key" in msg:
            return AuthFailed
        if "timeout" in msg or "timed out" in msg:
            return Timeout
        return ProviderError

# Global singleton
llm_failover = FailoverRouter(ProfileManager())


# ══════════════════════════════════════════════════════════════════════════════
# NEW: Config-driven FailoverManager (added by config migration)
#   Import: from core.llm_failover import get_failover_manager
#
#   All config from config_registry:
#     failover.enabled         = False   (off by default)
#     failover.openai_api_key  = ""      (empty = no OpenAI)
#     failover.anthropic_api_key = ""    (empty = no Anthropic)
#     failover.openai_model    = "gpt-4o-mini"
#     failover.anthropic_model = "claude-3-haiku-20240307"
#     failover.cooldown_seconds = 60
#     failover.max_retries     = 3
# ══════════════════════════════════════════════════════════════════════════════

import time as _time


class FailoverManager:
    """
    Simplified failover manager — reads all config from config_registry.
    Off by default (failover.enabled = False).
    """

    def __init__(self):
        self._failed_at: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        from core.config_registry import config
        return config.get("failover.enabled")

    @property
    def cooldown(self) -> int:
        from core.config_registry import config
        return config.get("failover.cooldown_seconds")

    def get_failover_providers(self) -> list[dict]:
        from core.config_registry import config
        if not self.enabled:
            return []
        providers = []
        openai_key = config.get("failover.openai_api_key")
        if openai_key:
            providers.append({
                "name": "openai",
                "api_key": openai_key,
                "model": config.get("failover.openai_model"),
                "base_url": "https://api.openai.com/v1",
            })
        anthropic_key = config.get("failover.anthropic_api_key")
        if anthropic_key:
            providers.append({
                "name": "anthropic",
                "api_key": anthropic_key,
                "model": config.get("failover.anthropic_model"),
                "base_url": "https://api.anthropic.com",
            })
        return providers

    def should_failover(self, provider: str) -> bool:
        if not self.enabled:
            return False
        last_fail = self._failed_at.get(provider, 0)
        return (_time.time() - last_fail) > self.cooldown

    def mark_failed(self, provider: str) -> None:
        self._failed_at[provider] = _time.time()
        logger.warning(f"Failover: marked '{provider}' as failed, cooldown {self.cooldown}s")

    def mark_recovered(self, provider: str) -> None:
        self._failed_at.pop(provider, None)
        logger.info(f"Failover: '{provider}' recovered")

    async def call_with_failover(
        self,
        primary_call,
        messages: list,
        **kwargs
    ) -> Any:
        try:
            return await primary_call(messages, **kwargs)
        except Exception as primary_err:
            logger.warning(f"Primary LLM failed: {primary_err}")
            if not self.enabled:
                raise primary_err
            providers = self.get_failover_providers()
            if not providers:
                raise primary_err
            for provider in providers:
                name = provider["name"]
                if not self.should_failover(name):
                    continue
                try:
                    logger.info(f"Failing over to {name}/{provider['model']}")
                    response = await self._call_cloud(provider, messages, **kwargs)
                    self.mark_recovered(name)
                    return response
                except Exception as e:
                    logger.error(f"Failover to {name} also failed: {e}")
                    self.mark_failed(name)
            raise RuntimeError("All failover providers exhausted")

    async def _call_cloud(self, provider: dict, messages: list, **kwargs) -> str:
        name = provider["name"]
        if name == "openai":
            return await self._call_openai(provider, messages, **kwargs)
        elif name == "anthropic":
            return await self._call_anthropic(provider, messages, **kwargs)
        else:
            raise ValueError(f"Unknown failover provider: {name}")

    async def _call_openai(self, provider: dict, messages: list, **kwargs) -> str:
        import httpx
        headers = {
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": provider["model"],
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 2048),
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{provider['base_url']}/chat/completions",
                headers=headers, json=payload
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]

    async def _call_anthropic(self, provider: dict, messages: list, **kwargs) -> str:
        import httpx
        headers = {
            "x-api-key": provider["api_key"],
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        system = ""
        filtered_messages = []
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content", "")
            else:
                filtered_messages.append(m)
        payload = {
            "model": provider["model"],
            "messages": filtered_messages,
            "max_tokens": kwargs.get("max_tokens", 2048),
        }
        if system:
            payload["system"] = system
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{provider['base_url']}/v1/messages",
                headers=headers, json=payload
            )
            r.raise_for_status()
            data = r.json()
            return data["content"][0]["text"]


_failover_manager = FailoverManager()


def get_failover_manager() -> FailoverManager:
    return _failover_manager
