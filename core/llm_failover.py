from __future__ import annotations

import asyncio
import logging
import time
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type, Set

from core.config_schema import jarvis_config, AuthProfile
from core.result import Ok, Err, Result
from core.errors import LLMError, Timeout, ProviderError, RateLimited, AuthFailed

logger = logging.getLogger("jarvis.core.llm_failover")

class ProfileManager:
    """Manages LLM AuthProfiles, priorities, discovery, and cooldown states."""

    def __init__(self):
        self.config = jarvis_config.failover
        self._profiles: List[AuthProfile] = []
        self._cooldowns: Dict[str, float] = {}  # profile_name -> wakeup_time
        self._failure_counts: Dict[str, int] = {}  # profile_name -> sequential failure count
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

    async def get_next_profile(self, provider: Optional[str] = None) -> Optional[AuthProfile]:
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

    def _get_profile(self, name: str) -> Optional[AuthProfile]:
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
        self._task: Optional[asyncio.Task] = None

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

    async def complete(self, model_group: str, messages: List[Dict], **kwargs) -> Result[str, LLMError]:
        """Perform completion with retry and failover logic."""
        from core.llm_router import get_router
        
        tried_profiles: Set[str] = set()
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
    def _classify_error(e: Exception) -> Type[LLMError]:
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
