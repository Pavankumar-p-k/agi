from __future__ import annotations

import base64
import io
import logging
import os

logger = logging.getLogger(__name__)


class ImageGenerator:
    """Image generation via provider APIs — matching OpenClaw's image generation system."""

    def __init__(self):
        self._provider = None
        self._detect_provider()

    def _detect_provider(self):
        if os.getenv("OPENAI_API_KEY"):
            self._provider = "openai"
        elif os.getenv("STABILITY_API_KEY"):
            self._provider = "stability"
        elif os.getenv("REPLICATE_API_TOKEN"):
            self._provider = "replicate"
        elif os.getenv("TOGETHER_API_KEY"):
            self._provider = "together"
        else:
            self._provider = None

    async def generate(self, prompt: str, size: str = "1024x1024",
                       n: int = 1, style: str = "vivid") -> list[str]:
        if self._provider == "openai":
            return await self._generate_openai(prompt, size, n, style)
        elif self._provider == "stability":
            return await self._generate_stability(prompt, size, n)
        elif self._provider == "replicate":
            return await self._generate_replicate(prompt)
        elif self._provider == "together":
            return await self._generate_together(prompt)
        logger.warning("[ImageGen] No provider configured")
        return []

    async def _generate_openai(self, prompt: str, size: str, n: int, style: str) -> list[str]:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            resp = await client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size=size,
                n=n,
                quality=style,
            )
            return [img.url for img in resp.data if img.url]
        except Exception as e:
            logger.warning("[ImageGen] OpenAI failed: %s", e)
            return []

    async def _generate_stability(self, prompt: str, size: str, n: int) -> list[str]:
        try:
            import httpx
            width, height = size.split("x")
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
                    headers={
                        "Authorization": f"Bearer {os.getenv('STABILITY_API_KEY')}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "text_prompts": [{"text": prompt, "weight": 1}],
                        "cfg_scale": 7,
                        "height": int(height),
                        "width": int(width),
                        "samples": n,
                        "steps": 30,
                    },
                )
                data = resp.json()
                urls = []
                for i, img in enumerate(data.get("artifacts", [])):
                    b64 = img.get("base64", "")
                    if b64:
                        urls.append(f"data:image/png;base64,{b64}")
                return urls
        except Exception as e:
            logger.warning("[ImageGen] Stability failed: %s", e)
            return []

    async def _generate_replicate(self, prompt: str) -> list[str]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    "https://api.replicate.com/v1/predictions",
                    headers={
                        "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "version": "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
                        "input": {"prompt": prompt},
                    },
                )
                data = resp.json()
                return [data.get("urls", {}).get("get", "")]
        except Exception as e:
            logger.warning("[ImageGen] Replicate failed: %s", e)
            return []

    async def _generate_together(self, prompt: str) -> list[str]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.together.xyz/v1/images/generations",
                    headers={
                        "Authorization": f"Bearer {os.getenv('TOGETHER_API_KEY')}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "black-forest-labs/FLUX.1.1-pro",
                        "prompt": prompt,
                        "width": 1024,
                        "height": 1024,
                        "steps": 4,
                        "n": 1,
                    },
                )
                data = resp.json()
                return data.get("data", [{}])[0].get("url", [])
        except Exception as e:
            logger.warning("[ImageGen] Together failed: %s", e)
            return []


image_generator = ImageGenerator()
