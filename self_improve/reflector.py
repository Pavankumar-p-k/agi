from __future__ import annotations

import json
import time
from collections import defaultdict
from typing import Any

import httpx


REFLECT_SYSTEM = """You are JARVIS's self-improvement engine.
Analyze decision quality and return compact JSON:
{
  "key_insight": "",
  "recommendation": "",
  "confidence_adjustment": 0.0
}"""


class SelfReflector:
    def __init__(self, memory):
        self.memory = memory
        self._reflection_log: list[dict[str, Any]] = []
        self._action_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"success": 0, "fail": 0})
        self._model_quality: dict[str, list[float]] = defaultdict(list)

    async def reflect(self, decisions: list[dict[str, Any]], state) -> dict[str, Any]:
        if not decisions:
            return {}

        for d in decisions:
            action = str(d.get("action", "unknown"))
            if d.get("success") is True:
                self._action_stats[action]["success"] += 1
            else:
                self._action_stats[action]["fail"] += 1

            model = str(d.get("model", "")).strip()
            quality = d.get("quality")
            if model and isinstance(quality, (int, float)):
                self._model_quality[model].append(float(quality))

        total_success = sum(item["success"] for item in self._action_stats.values())
        total_fail = sum(item["fail"] for item in self._action_stats.values())
        total = total_success + total_fail
        success_rate = (total_success / total) if total else 0.0

        best_action = ""
        worst_action = ""
        if self._action_stats:
            best_action = max(self._action_stats, key=lambda a: self._action_stats[a]["success"])
            worst_action = max(self._action_stats, key=lambda a: self._action_stats[a]["fail"])

        insight = await self._ask_llm_to_reflect(decisions[-20:], success_rate)
        reflection = {
            "timestamp": time.time(),
            "decisions_analyzed": len(decisions),
            "success_rate": round(success_rate, 3),
            "best_action": best_action,
            "worst_action": worst_action,
            "insight": insight,
            "state_hour": getattr(state, "hour", -1),
            "state_mood": getattr(state, "pavan_mood", "neutral"),
        }
        self._reflection_log.append(reflection)
        await self.memory.save_reflection(reflection)
        return reflection

    async def _ask_llm_to_reflect(self, decisions: list[dict[str, Any]], success_rate: float) -> dict[str, Any]:
        payload = {
            "success_rate": round(success_rate, 3),
            "recent": [
                {
                    "action": d.get("action"),
                    "success": d.get("success"),
                    "confidence": d.get("confidence"),
                }
                for d in decisions[-10:]
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                res = await client.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": "phi3:mini",
                        "system": REFLECT_SYSTEM,
                        "prompt": f"Analyze:\n{json.dumps(payload)}",
                        "stream": False,
                        "options": {
                            "num_predict": 120,
                            "temperature": 0.2,
                            "num_gpu": 99,
                        },
                    },
                )
                raw = str(res.json().get("response", "")).strip()
                start = raw.find("{")
                end = raw.rfind("}")
                if start != -1 and end > start:
                    return json.loads(raw[start : end + 1])
        except Exception:
            pass
        return {"key_insight": "", "recommendation": "", "confidence_adjustment": 0.0}

    def get_stats(self) -> dict[str, Any]:
        model_accuracy = {}
        for model, scores in self._model_quality.items():
            if scores:
                model_accuracy[model] = round(sum(scores) / len(scores), 3)
        return {
            "action_stats": dict(self._action_stats),
            "model_accuracy": model_accuracy,
            "reflections_done": len(self._reflection_log),
        }

