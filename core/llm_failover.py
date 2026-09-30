"""LLM provider failover: profile management, cooldowns and routing.

Profiles are discovered from configuration (``failover.profiles``) and from
well-known provider environment variables. When a provider call fails the
profile is put on an exponential-backoff cooldown and the next-highest
priority available profile is used instead. A background probe re-tests
cooled-down profiles so recovered providers rejoin the rotation.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from core.config_schema import AuthProfile
from core.configuration import configuration
from core.errors import AuthFailed, ProviderError, RateLimited, Timeout
from core.result import Err, Ok, err_from

logger = logging.getLogger(__name__)

# env var -> (provider name, priority)
_ENV_PROVIDERS: Dict[str, tuple[str, int]] = {
    "OPENAI_API_KEY": ("openai", 10),
    "ANTHROPIC_API_KEY": ("anthropic", 8),
    "GEMINI_API_KEY": ("gemini", 6),
    "GROQ_API_KEY": ("groq", 4),
    "TOGETHER_API_KEY": ("together", 2),
}


class ProfileManager:
    """Owns the set of provider profiles and their cooldown state."""

    def __init__(self) -> None:
        self._profiles: List[AuthProfile] = []
        self._cooldowns: Dict[str, float] = {}
        self._failure_counts: Dict[str, int] = {}
        self._vault_loaded: bool = False
        self._load_from_vault()
        self._discover_profiles()

    # ------------------------------------------------------------------ setup
    def _load_from_vault(self) -> None:
        """Fill missing api_keys from the environment/vault (one-shot)."""
        if self._vault_loaded:
            return
        # Environment credentials are consulted in _discover_profiles; a real
        # vault integration can hook in here without changing the contract.
        self._vault_loaded = True

    def _discover_profiles(self) -> List[AuthProfile]:
        profiles: List[AuthProfile] = []
        configured = configuration.get("failover.profiles", []) or []
        profiles.extend(configured)
        for env_key, (provider, priority) in _ENV_PROVIDERS.items():
            key = os.getenv(env_key, "")
            if not key:
                continue
            if any(p.provider == provider for p in profiles):
                continue
            profiles.append(AuthProfile(name=provider, provider=provider,
                                        api_key=key, priority=priority))
        self._profiles = profiles
        return list(profiles)

    # --------------------------------------------------------------- cooldown
    async def set_cooldown(self, name: str, error: str = "") -> float:
        """Record a failure for *name* and set its wakeup time."""
        count = self._failure_counts.get(name, 0) + 1
        self._failure_counts[name] = count
        base = float(configuration.get("failover.cooldown_backoff_base", 60))
        delay = base * (2 ** (count - 1))
        self._cooldowns[name] = time.time() + delay
        if error:
            logger.warning("Profile %s failed (%s); cooldown %.0fs", name, error, delay)
        return self._cooldowns[name]

    def clear_cooldown(self, name: str) -> None:
        self._cooldowns.pop(name, None)
        self._failure_counts[name] = 0

    async def get_next_profile(self) -> Optional[AuthProfile]:
        """Highest-priority profile that is not cooling down."""
        now = time.time()
        candidates = [p for p in self._profiles
                      if p.enabled and self._cooldowns.get(p.name, 0) <= now]
        if not candidates:
            return None
        candidates.sort(key=lambda p: -p.priority)
        return candidates[0]


class FailoverRouter:
    """Routes completions across profiles, failing over on provider errors."""

    def __init__(self, profile_manager: ProfileManager) -> None:
        self._pm = profile_manager

    def _classify_error(self, exc: Exception) -> type:
        text = str(exc).lower()
        if "429" in text or "rate limit" in text:
            return RateLimited
        if "401" in text or "unauthorized" in text or "auth" in text:
            return AuthFailed
        if "timeout" in text or "timed out" in text:
            return Timeout
        return ProviderError

    async def complete(self, role: str, messages: List[dict], **kwargs: Any):
        """Try profiles in priority order until one succeeds."""
        from core.llm_router import get_router

        last_exc: Optional[Exception] = None
        while True:
            profile = await self._pm.get_next_profile()
            if profile is None:
                if last_exc is None:
                    return err_from(ProviderError("No failover profiles available"),
                                    code="FAILOVER_NO_PROFILES")
                return err_from(last_exc, code="FAILOVER_EXHAUSTED")
            try:
                response = await get_router().acompletion(
                    model=profile.model or role, messages=messages, **kwargs)
                text = response.choices[0].message.content
                self._pm._failure_counts[profile.name] = 0
                return Ok(text)
            except Exception as exc:  # noqa: BLE001 - any provider error fails over
                last_exc = exc
                category = self._classify_error(exc)
                logger.info("Profile %s failed (%s: %s); failing over",
                            profile.name, category.__name__, exc)
                await self._pm.set_cooldown(profile.name, str(exc))


class CooldownProbe:
    """Background loop that re-tests cooled-down profiles and revives them."""

    def __init__(self, profile_manager: ProfileManager, interval: float = 30.0) -> None:
        self._pm = profile_manager
        self._interval = interval
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def _probe(self, name: str) -> bool:
        """Health-check a profile with a tiny completion."""
        try:
            from core.llm_router import get_router

            profile = next((p for p in self._pm._profiles if p.name == name), None)
            model = profile.model or (profile.provider if profile else "chat")
            response = await get_router().acompletion(
                model=model, messages=[{"role": "user", "content": "ping"}])
            return bool(getattr(response, "choices", None))
        except Exception:  # noqa: BLE001 - probing must never raise
            return False

    async def _loop(self) -> None:
        while self._running:
            now = time.time()
            for name, wakeup in list(self._pm._cooldowns.items()):
                if wakeup > now:
                    continue
                try:
                    ok = await self._probe(name)
                except Exception:  # noqa: BLE001
                    ok = False
                if ok:
                    self._pm._cooldowns.pop(name, None)
                    self._pm._failure_counts[name] = 0
                    logger.info("Profile %s recovered; cooldown cleared", name)
            await asyncio.sleep(self._interval)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001 - probing shutdown must never raise
                pass
