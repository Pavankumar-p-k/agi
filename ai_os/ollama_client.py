import requests, logging
from typing import Any

log = logging.getLogger("ai_os.ollama")


class OllamaClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def generate(self, model: str, prompt: str, max_tokens: int = 512, temperature: float = 0.2) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        r = requests.post(url, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        if "choices" in data and len(data["choices"]) > 0:
            text = data["choices"][0].get("message", {}).get("content", "")
            return text.strip()
        return ""

    def status(self) -> dict[str, Any]:
        try:
            r = requests.get(f"{self.base_url}/v1/models", timeout=10)
            r.raise_for_status()
            return {"models": r.json()}
        except Exception as e:
            log.exception("Ollama status failed")
            return {"error": str(e)}
