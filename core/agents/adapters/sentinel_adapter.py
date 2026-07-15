from __future__ import annotations

import json
import logging
import time

from core.agents._sub_agent_base import AgentResult, SubAgent
from core.agents.adapters.base_adapter import SubAgentAdapter
from core.agents.capabilities import CAPABILITIES

logger = logging.getLogger(__name__)

try:
    import psutil
except ImportError:
    psutil = None

SENTINEL_PROMPTS = {
    "diagnose": (
        "You are SENTINEL, a system monitoring sub-agent inside Jarvis — Pavan's personal AI OS. "
        "You receive real-time system metrics. Your role: diagnose issues and recommend actions. "
        "Output: System Health Score (0-100), Critical Issues (if any), "
        "Warning Signs, Root Cause Analysis for any anomaly, "
        "Immediate Actions (numbered), Preventive measures. "
        "Think like a DevOps SRE who's done 100 incident postmortems."
    ),
    "optimize": (
        "You are SENTINEL in Optimize Mode inside Jarvis — Pavan's personal AI OS. "
        "You receive system metrics. Your role: identify optimization opportunities. "
        "Output: Top 5 optimizations ranked by impact, each with: "
        "What to optimize, How to do it (specific command or code), "
        "Expected improvement, Risk level. Focus on quick wins first."
    ),
    "predict": (
        "You are SENTINEL in Predictive Mode inside Jarvis — Pavan's personal AI OS. "
        "You receive historical system metrics. Your role: predict future issues. "
        "Output: Predicted Issues (with probability %), Time to Impact (hours/days), "
        "Early warning signs to watch, Preventive actions to take now. "
        "Base predictions on trends, not just current state."
    ),
    "report": (
        "You are SENTINEL in Report Mode inside Jarvis — Pavan's personal AI OS. "
        "You receive a period of system metrics. Your role: generate a health report. "
        "Output: Period summary, Uptime %, Peak usage times, "
        "Incidents (if any), Average performance vs baseline, "
        "Recommendations for next period. Format like a weekly ops review."
    ),
}

class SentinelAgent(SubAgent):
    NAME = "SENTINEL"
    DESCRIPTION = "System health monitoring, diagnostics, optimization, and predictive analysis"
    DEFAULT_MODE = "diagnose"
    AVAILABLE_MODES = ["diagnose", "optimize", "predict", "report"]
    MAX_TOKENS = 1500

    def get_system_prompt(self, mode: str) -> str:
        return SENTINEL_PROMPTS.get(mode, SENTINEL_PROMPTS["diagnose"])

    async def run(self, task: str = "check system", mode: str | None = None, **kwargs) -> AgentResult:
        metrics = await self._collect_metrics()
        enriched_task = f"CURRENT SYSTEM METRICS:\n{json.dumps(metrics, indent=2)}\n\nUSER QUERY: {task}"
        return await super().run(enriched_task, mode=mode, **kwargs)

    async def _collect_metrics(self) -> dict:
        if psutil is None:
            return {"error": "psutil not installed"}
        try:
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            net = psutil.net_io_counters()
            procs = sorted(psutil.process_iter(["pid","name","cpu_percent","memory_percent"]),
                          key=lambda p: (p.info["cpu_percent"] or 0), reverse=True)[:5]
            return {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "cpu_percent": cpu,
                "cpu_count": psutil.cpu_count(),
                "memory": {"total_gb": round(mem.total/1e9,1), "used_pct": mem.percent,
                           "available_gb": round(mem.available/1e9,1)},
                "disk": {"total_gb": round(disk.total/1e9,1), "used_pct": disk.percent},
                "network": {"bytes_sent_mb": round(net.bytes_sent/1e6,1),
                            "bytes_recv_mb": round(net.bytes_recv/1e6,1)},
                "top_processes": [{"name": p.info["name"], "cpu_pct": p.info["cpu_percent"],
                                   "mem_pct": round(p.info["memory_percent"] or 0, 1)}
                                  for p in procs],
            }
        except Exception as e:
            logger.error("Sentinel agent failed: %s", e, exc_info=True)
            return {"error": "Operation failed"}


class SentinelAdapter(SubAgentAdapter):
    agent_id = "sentinel"
    capabilities = CAPABILITIES["sentinel"]
    sub_agent_class = SentinelAgent
    default_mode = "diagnose"
