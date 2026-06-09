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

import pytest
import asyncio
import time
import os
from unittest.mock import MagicMock, AsyncMock, patch

from core.llm_failover import ProfileManager, FailoverRouter, CooldownProbe
from core.config_schema import AuthProfile, jarvis_config
from core.errors import RateLimited, AuthFailed, Timeout, ProviderError
from core.result import Ok, Err

@pytest.fixture
def profile_manager():
    # Mock config and isolate from real env vars
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": "",
        "GROQ_API_KEY": "", "TOGETHER_API_KEY": "",
    }, clear=False):
        jarvis_config.failover.profiles = [
            AuthProfile(name="test_openai", api_key="sk-123", provider="openai", priority=10),
            AuthProfile(name="test_anthropic", api_key="ant-456", provider="anthropic", priority=5),
        ]
        pm = ProfileManager()
        # Reset state
        pm._cooldowns = {}
        pm._failure_counts = {}
        pm._vault_loaded = True # Skip vault loading
        return pm

@pytest.mark.asyncio
async def test_profile_manager_discovery(profile_manager):
    # Discovery from env vars
    with patch.dict(os.environ, {"GROQ_API_KEY": "g-789"}):
        pm = ProfileManager()
        profiles = pm._discover_profiles()
        assert any(p.name == "groq" for p in profiles)
        assert any(p.provider == "groq" for p in profiles)

@pytest.mark.asyncio
async def test_profile_manager_cooldown(profile_manager):
    await profile_manager.set_cooldown("test_openai")
    assert "test_openai" in profile_manager._cooldowns
    assert profile_manager._failure_counts["test_openai"] == 1
    
    # Check exponential backoff (base 60)
    wakeup1 = profile_manager._cooldowns["test_openai"]
    
    await profile_manager.set_cooldown("test_openai")
    assert profile_manager._failure_counts["test_openai"] == 2
    wakeup2 = profile_manager._cooldowns["test_openai"]
    
    # Duration should be approx 120s now (first: 60s, second: 120s)
    assert (wakeup2 - wakeup1) >= 60

@pytest.mark.asyncio
async def test_profile_manager_get_next(profile_manager):
    # test_openai has priority 10
    p = await profile_manager.get_next_profile()
    assert p.name == "test_openai"
    
    # Cooldown test_openai
    await profile_manager.set_cooldown("test_openai")
    
    # Should get test_anthropic (priority 5)
    p = await profile_manager.get_next_profile()
    assert p.name == "test_anthropic"

@pytest.mark.asyncio
async def test_failover_router_classify(profile_manager):
    router = FailoverRouter(profile_manager)
    
    assert router._classify_error(Exception("429 Too Many Requests")) == RateLimited
    assert router._classify_error(Exception("401 Unauthorized")) == AuthFailed
    assert router._classify_error(Exception("timeout error")) == Timeout
    assert router._classify_error(Exception("unknown error")) == ProviderError

@pytest.mark.asyncio
async def test_failover_router_success(profile_manager):
    router = FailoverRouter(profile_manager)
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Success"
    
    with patch("core.llm_router.get_router") as mock_get_router:
        mock_router = MagicMock()
        mock_router.acompletion = AsyncMock(return_value=mock_response)
        mock_get_router.return_value = mock_router
        
        result = await router.complete("chat", [{"role": "user", "content": "hi"}])
        assert result.is_ok()
        assert result.unwrap() == "Success"
        assert mock_router.acompletion.call_count == 1

@pytest.mark.asyncio
async def test_failover_router_fallback(profile_manager):
    router = FailoverRouter(profile_manager)
    
    # test_openai fails, test_anthropic succeeds
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Anthropic Success"
    
    with patch("core.llm_router.get_router") as mock_get_router:
        mock_router = MagicMock()
        mock_router.acompletion = AsyncMock()
        mock_router.acompletion.side_effect = [
            Exception("429 Rate Limit"),
            mock_response
        ]
        mock_get_router.return_value = mock_router
        
        result = await router.complete("chat", [{"role": "user", "content": "hi"}])
        assert result.is_ok()
        assert result.unwrap() == "Anthropic Success"
        assert mock_router.acompletion.call_count == 2
        # Verify test_openai was cooldowned
        assert "test_openai" in profile_manager._cooldowns

@pytest.mark.asyncio
async def test_cooldown_probe_recovery(profile_manager):
    probe = CooldownProbe(profile_manager, interval=0.1)
    
    await profile_manager.set_cooldown("test_openai")
    # Force wakeup time to past
    profile_manager._cooldowns["test_openai"] = time.time() - 10
    
    with patch.object(CooldownProbe, "_probe", AsyncMock(return_value=True)):
        await probe.start()
        await asyncio.sleep(0.5)
        await probe.stop()
        
    assert "test_openai" not in profile_manager._cooldowns
    assert profile_manager._failure_counts.get("test_openai", 0) == 0
