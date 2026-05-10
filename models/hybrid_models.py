# backend/models/hybrid_models.py
"""
Hybrid Model Integration Layer
Supports: Ollama (local) → Codex CLI → Claude → Copilot (online)
Automatic fallbacks with reasoning and execution tracking
"""

import asyncio
import json
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import httpx
try:
    import openai
except ImportError:  # pragma: no cover
    openai = None
try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover
    Anthropic = None
import requests

from core.config import CLAUDE_API_KEY, COPILOT_API_KEY, CODEX_CLI_PATH
from core.model_router import ROLE_MODELS, MODEL_ALIASES
from core.types import ModelResult


class ModelProvider(Enum):
    OLLAMA = "ollama"
    CODEX_CLI = "codex_cli"
    CLAUDE = "claude"
    COPILOT = "copilot"


class TaskType(Enum):
    PLANNING = "planning"
    REASONING = "reasoning"
    EXECUTION = "execution"
    CODING = "coding"
    ANALYSIS = "analysis"
    CREATIVE = "creative"
    VISION = "vision"


@dataclass
class HybridConfig:
    max_retries: int = 3
    timeout_seconds: int = 30
    fallback_chain: List[ModelProvider] = None

    def __post_init__(self):
        if self.fallback_chain is None:
            self.fallback_chain = [
                ModelProvider.OLLAMA,
                ModelProvider.CODEX_CLI,
                ModelProvider.CLAUDE,
                ModelProvider.COPILOT
            ]


class HybridModelManager:
    """
    Research-grade hybrid model manager with automatic fallbacks
    Implements the orchestration layer from Perplexity-style systems
    """

    def __init__(self):
        self.config = HybridConfig()
        self._clients = {}
        self._performance_stats = {}
        self._fallback_history = []

        # Initialize clients
        self._init_clients()

    def _init_clients(self):
        """Initialize all model clients"""
        # Ollama client (already exists)
        self._clients[ModelProvider.OLLAMA] = httpx.AsyncClient(timeout=60.0)

        # Codex CLI (local executable)
        if CODEX_CLI_PATH and os.path.exists(CODEX_CLI_PATH):
            self._clients[ModelProvider.CODEX_CLI] = True

        # Claude API
        if Anthropic is not None and CLAUDE_API_KEY:
            self._clients[ModelProvider.CLAUDE] = Anthropic(api_key=CLAUDE_API_KEY)

        # Copilot API (GitHub Copilot)
        if openai is not None and COPILOT_API_KEY:
            self._clients[ModelProvider.COPILOT] = openai.OpenAI(
                api_key=COPILOT_API_KEY,
                base_url="https://api.github.com/copilot"  # Placeholder - actual endpoint may vary
            )

    async def generate_with_fallback(
        self,
        prompt: str,
        task_type: TaskType,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        images: List[str] = None
    ) -> ModelResult:
        """
        Generate response with automatic fallback chain
        Returns the best available result with fallback tracking
        """

        start_time = time.time()
        errors = []

        for provider in self.config.fallback_chain:
            if provider not in self._clients:
                continue

            try:
                result = await self._call_provider(
                    provider, prompt, task_type, system_prompt,
                    temperature, max_tokens, images
                )

                if result and not result.error:
                    # Track successful fallback
                    if len(errors) > 0:
                        result.fallback_reason = f"Previous providers failed: {', '.join(errors)}"

                    self._update_performance_stats(provider, result.latency_ms, True)
                    return result

            except Exception as e:
                error_msg = f"{provider.value}: {str(e)}"
                errors.append(error_msg)
                self._update_performance_stats(provider, int((time.time() - start_time) * 1000), False)

        # All providers failed
        return ModelResult(
            provider=ModelProvider.OLLAMA,
            model="fallback",
            response="All model providers failed. System unavailable.",
            confidence=0.0,
            latency_ms=int((time.time() - start_time) * 1000),
            tokens_used=0,
            error=f"Total failures: {len(errors)}",
            fallback_reason="; ".join(errors)
        )

    async def _call_provider(
        self,
        provider: ModelProvider,
        prompt: str,
        task_type: TaskType,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
        images: List[str]
    ) -> ModelResult:

        start_time = time.time()

        if provider == ModelProvider.OLLAMA:
            return await self._call_ollama(prompt, task_type, system_prompt, temperature, max_tokens, images)

        elif provider == ModelProvider.CODEX_CLI:
            return await self._call_codex_cli(prompt, task_type, system_prompt, temperature, max_tokens)

        elif provider == ModelProvider.CLAUDE:
            return await self._call_claude(prompt, task_type, system_prompt, temperature, max_tokens)

        elif provider == ModelProvider.COPILOT:
            return await self._call_copilot(prompt, task_type, system_prompt, temperature, max_tokens)

    async def _call_ollama(
        self,
        prompt: str,
        task_type: TaskType,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
        images: List[str]
    ) -> ModelResult:

        # Get best Ollama model for task
        model = self._get_ollama_model_for_task(task_type)

        from core.model_router import get_ollama_url
        url = f"{get_ollama_url(model)}/api/generate"

        payload = {
            "model": model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 4096
            }
        }

        if images:
            payload["images"] = images

        start_time = time.time()
        async with self._clients[ModelProvider.OLLAMA] as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        latency = int((time.time() - start_time) * 1000)

        return ModelResult(
            provider=ModelProvider.OLLAMA,
            model=model,
            response=data.get("response", ""),
            confidence=self._estimate_confidence(data),
            latency_ms=latency,
            tokens_used=data.get("eval_count", 0)
        )

    async def _call_codex_cli(
        self,
        prompt: str,
        task_type: TaskType,
        system_prompt: str,
        temperature: float,
        max_tokens: int
    ) -> ModelResult:

        # Codex CLI integration
        cmd = [
            CODEX_CLI_PATH,
            "query",
            "--prompt", prompt,
            "--system", system_prompt,
            "--temperature", str(temperature),
            "--max-tokens", str(max_tokens),
            "--json"
        ]

        start_time = time.time()
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()
        latency = int((time.time() - start_time) * 1000)

        if process.returncode != 0:
            raise Exception(f"Codex CLI failed: {stderr.decode()}")

        try:
            data = json.loads(stdout.decode())
            return ModelResult(
                provider=ModelProvider.CODEX_CLI,
                model="codex-cli",
                response=data.get("response", ""),
                confidence=data.get("confidence", 0.8),
                latency_ms=latency,
                tokens_used=data.get("tokens_used", 0)
            )
        except json.JSONDecodeError:
            raise Exception("Invalid JSON response from Codex CLI")

    async def _call_claude(
        self,
        prompt: str,
        task_type: TaskType,
        system_prompt: str,
        temperature: float,
        max_tokens: int
    ) -> ModelResult:

        client = self._clients[ModelProvider.CLAUDE]

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        start_time = time.time()
        response = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=max_tokens,
            temperature=temperature,
            messages=messages
        )
        latency = int((time.time() - start_time) * 1000)

        return ModelResult(
            provider=ModelProvider.CLAUDE,
            model="claude-3-sonnet",
            response=response.content[0].text,
            confidence=0.95,  # Claude typically high confidence
            latency_ms=latency,
            tokens_used=response.usage.input_tokens + response.usage.output_tokens
        )

    async def _call_copilot(
        self,
        prompt: str,
        task_type: TaskType,
        system_prompt: str,
        temperature: float,
        max_tokens: int
    ) -> ModelResult:

        client = self._clients[ModelProvider.COPILOT]

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        start_time = time.time()
        response = client.chat.completions.create(
            model="gpt-4",  # Copilot typically uses GPT-4
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        latency = int((time.time() - start_time) * 1000)

        return ModelResult(
            provider=ModelProvider.COPILOT,
            model="copilot-gpt4",
            response=response.choices[0].message.content,
            confidence=0.9,
            latency_ms=latency,
            tokens_used=response.usage.total_tokens
        )

    def _get_ollama_model_for_task(self, task_type: TaskType) -> str:
        """Map task types to best Ollama models"""
        mapping = {
            TaskType.PLANNING: "deepseek-r1:1.5b",
            TaskType.REASONING: "deepseek-r1:1.5b",
            TaskType.EXECUTION: "qwen3:4b",
            TaskType.CODING: "qwen2.5-coder:3b",
            TaskType.ANALYSIS: "qwen2.5:7b",
            TaskType.CREATIVE: "mistral:7b",
            TaskType.VISION: "moondream"
        }
        return mapping.get(task_type, "llama3.1:8b")

    def _estimate_confidence(self, ollama_response: dict) -> float:
        """Estimate confidence from Ollama response"""
        # Simple heuristic based on response characteristics
        response = ollama_response.get("response", "")
        if len(response.strip()) < 10:
            return 0.3
        elif len(response.strip()) > 100:
            return 0.8
        else:
            return 0.6

    def _update_performance_stats(self, provider: ModelProvider, latency: int, success: bool):
        """Update performance tracking"""
        key = provider.value
        if key not in self._performance_stats:
            self._performance_stats[key] = {"calls": 0, "successes": 0, "total_latency": 0}

        stats = self._performance_stats[key]
        stats["calls"] += 1
        stats["total_latency"] += latency
        if success:
            stats["successes"] += 1

    def get_performance_report(self) -> Dict[str, Any]:
        """Get performance statistics for monitoring"""
        report = {}
        for provider, stats in self._performance_stats.items():
            calls = stats["calls"]
            if calls > 0:
                success_rate = stats["successes"] / calls
                avg_latency = stats["total_latency"] / calls
                report[provider] = {
                    "success_rate": success_rate,
                    "average_latency_ms": avg_latency,
                    "total_calls": calls
                }
        return report


# Global instance
hybrid_manager = HybridModelManager()