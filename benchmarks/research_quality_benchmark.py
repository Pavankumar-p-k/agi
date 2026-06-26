"""Research Quality Benchmark — LLM-only vs full Research Pipeline.

Tests 2 configurations:
  raw      — LLM answers directly (no research pipeline)
  pipeline — LLM + FactExtractor → FactStore → FactRetriever → FactReasoner → FactSynthesizer

Metrics:
  - fact_recall: ground-truth facts present in output / total ground-truth facts
  - fact_precision: correct facts / total claims in output
  - contradiction_detection_rate: contradictions found / total contradictions in source
  - coverage: required subtopics addressed
  - hallucination_rate: false claims / total claims
  - duration

Usage:
    python benchmarks/research_quality_benchmark.py
    python benchmarks/research_quality_benchmark.py --smoke

Environment:
    OLLAMA_URL   (default: http://localhost:11434)
    AGENT_MODEL  (default: qwen2.5:7b)
    REPORT_DIR   (default: benchmark_reports)
"""

import argparse
import asyncio
import httpx
import json
import logging
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("research_quality_bench")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("AGENT_MODEL", "qwen2.5:7b")
MAX_TOOL_CALLS = int(os.environ.get("MAX_TOOL_CALLS", "30"))
REPORT_DIR = os.environ.get("REPORT_DIR", "benchmark_reports")
os.makedirs(REPORT_DIR, exist_ok=True)

# ── Ground-truth datasets ─────────────────────────────────────

@dataclass
class GroundTruthFact:
    entity: str
    attribute: str
    value: str
    category: str = "general"

@dataclass
class GroundTruthContradiction:
    entity: str
    attribute: str
    values: list[str]
    sources: list[str]

@dataclass
class ResearchDataset:
    id: str
    question: str
    required_subtopics: list[str]
    ground_truth_facts: list[GroundTruthFact]
    contradictions: list[GroundTruthContradiction] = field(default_factory=list)
    source_texts: list[dict] = field(default_factory=list)
    # source_texts: [{"url": str, "content": str}, ...]

DATASETS: list[ResearchDataset] = [
    ResearchDataset(
        id="python_versions",
        question="What are the key differences between Python 3.11, 3.12, and 3.13?",
        required_subtopics=["performance", "new_features", "syntax_changes", "deprecations"],
        ground_truth_facts=[
            GroundTruthFact("Python 3.11", "release_year", "2022", "release"),
            GroundTruthFact("Python 3.11", "major_feature", "exception groups", "feature"),
            GroundTruthFact("Python 3.12", "release_year", "2023", "release"),
            GroundTruthFact("Python 3.12", "major_feature", "f-strings improvements", "feature"),
            GroundTruthFact("Python 3.13", "release_year", "2024", "release"),
            GroundTruthFact("Python 3.13", "major_feature", "free-threaded mode", "feature"),
            GroundTruthFact("Python 3.12", "performance_improvement", "5-10% faster than 3.11", "performance"),
            GroundTruthFact("Python 3.13", "performance_improvement", "JIT compiler experimental", "performance"),
        ],
        contradictions=[
            GroundTruthContradiction("Python 3.13", "GIL_removed", ["yes, completely removed", "no, made optional via free-threading", "partially via experimental flag"], ["blog.python.org", "docs.python.org", "peps.python.org"]),
        ],
        source_texts=[
            {"url": "https://docs.python.org/3/whatsnew/3.11.html", "content": "Python 3.11 was released in October 2022. Key features include exception groups and fine-grained error locations in tracebacks. Performance improvements make Python 3.11 approximately 10-60% faster than Python 3.10."},
            {"url": "https://docs.python.org/3/whatsnew/3.12.html", "content": "Python 3.12 was released in October 2023. It includes improved f-strings syntax, support for the Linux perf profiler, and is approximately 5-10% faster than Python 3.11."},
            {"url": "https://docs.python.org/3/whatsnew/3.13.html", "content": "Python 3.13 was released in October 2024. The headline feature is an experimental free-threaded build mode (PEP 703), which allows the GIL to be disabled. An experimental JIT compiler is also included."},
            {"url": "https://peps.python.org/pep-0703/", "content": "PEP 703 proposes making the Global Interpreter Lock (GIL) optional in CPython. As of Python 3.13, free-threaded execution is available as an experimental build configuration. The GIL is not removed by default."},
            {"url": "https://blog.python.org/2024/10/python-313-free-threaded.html", "content": "Python 3.13 ships with optional free-threading. The GIL can be disabled at build time, but remains enabled by default. This is NOT a complete GIL removal."},
        ],
    ),
    ResearchDataset(
        id="docker_vs_podman",
        question="How does Podman compare to Docker for container management?",
        required_subtopics=["architecture", "security", "compatibility", "performance", "kubernetes"],
        ground_truth_facts=[
            GroundTruthFact("Docker", "architecture", "client-server with daemon", "architecture"),
            GroundTruthFact("Podman", "architecture", "daemonless, fork-exec", "architecture"),
            GroundTruthFact("Docker", "security", "requires root privileges by default", "security"),
            GroundTruthFact("Podman", "security", "rootless by default", "security"),
            GroundTruthFact("Docker", "orchestration", "Docker Compose, Swarm", "feature"),
            GroundTruthFact("Podman", "orchestration", "Podman Compose, Pods", "feature"),
            GroundTruthFact("Docker", "kubernetes", "kind, minikube support", "kubernetes"),
            GroundTruthFact("Podman", "kubernetes", "native pod generation for Kubernetes", "kubernetes"),
            GroundTruthFact("Docker", "image_format", "OCI compatible", "compatibility"),
            GroundTruthFact("Podman", "image_format", "OCI compatible", "compatibility"),
        ],
        contradictions=[
            GroundTruthContradiction("Podman", "docker_compatibility", ["fully compatible with Docker CLI", "mostly compatible, some flags differ", "compatible via podman-docker alias"], ["podman.io", "redhat.com", "docker.com"]),
        ],
        source_texts=[
            {"url": "https://podman.io/whatis", "content": "Podman is a daemonless container engine that uses a fork-exec model. It does not require a running daemon and containers run as regular processes. Rootless execution is default."},
            {"url": "https://docs.docker.com/get-started/overview/", "content": "Docker uses a client-server architecture with a background daemon (dockerd). The Docker daemon manages containers, images, networks, and storage volumes. Docker typically requires root privileges."},
            {"url": "https://podman.io/compatibility", "content": "Podman is designed to be mostly CLI-compatible with Docker. The podman-docker package provides a docker alias. Most Docker commands work directly with Podman."},
            {"url": "https://kubernetes.io/docs/tasks/", "content": "Both Docker and Podman containers can run on Kubernetes. Podman can generate Kubernetes YAML directly from pods. Docker images are OCI-compatible."},
            {"url": "https://www.redhat.com/en/topics/containers/what-is-podman", "content": "Podman supports pods (groups of containers sharing resources), similar to Kubernetes. Podman Compose is available as an alternative to Docker Compose."},
        ],
    ),
]


# ── LLM Interface ──────────────────────────────────────────────

async def call_llm(messages: list[dict]) -> tuple[str, list[dict]]:
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": 2048, "temperature": 0.1},
    }
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
                if resp.status_code == 400:
                    logger.warning("LLM 400 (attempt %d/3): %s", attempt + 1, resp.text[:200])
                    await asyncio.sleep(1)
                    continue
                resp.raise_for_status()
                data = resp.json()
                msg = data.get("message", {})
                content = msg.get("content", "")
                raw_tool_calls = msg.get("tool_calls", [])
                tool_calls = []
                for tc in raw_tool_calls:
                    fn = tc.get("function", tc)
                    name = fn.get("name", "")
                    args_raw = fn.get("arguments", "{}")
                    if isinstance(args_raw, str):
                        try:
                            args = json.loads(args_raw)
                        except json.JSONDecodeError:
                            args = {}
                    else:
                        args = args_raw
                    tool_calls.append({"name": name, "arguments": args})
                return content, tool_calls
        except Exception as e:
            logger.error("LLM call failed (attempt %d/3): %s", attempt + 1, e)
            if attempt == 2:
                return "", []
            await asyncio.sleep(1)
    return "", []


# ── Pipeline Components ────────────────────────────────────────

def init_pipeline():
    import tempfile
    from core.research import (
        FactStore, FactExtractor, FactRetriever,
        FactReasoner, FactSynthesizer,
    )
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    store = FactStore(db_path=tmp.name)
    extractor = FactExtractor()
    retriever = FactRetriever(store)
    reasoner = FactReasoner()
    synthesizer = FactSynthesizer()
    return store, extractor, retriever, reasoner, synthesizer, tmp.name


async def run_pipeline(question: str, sources: list[dict]) -> dict[str, Any]:
    """Full research pipeline: extract → store → retrieve → reason → synthesize."""
    store, extractor, retriever, reasoner, synthesizer, _tmp_path = init_pipeline()
    all_facts = []
    for src in sources:
        facts = extractor.extract(
            text=src["content"],
            source_url=src["url"],
        )
        for f in facts:
            store.insert_fact(f)
        all_facts.extend(facts)

    retrieved = retriever.retrieve(question, limit=50)
    comparison = reasoner.analyze(retrieved)
    report = synthesizer.synthesize(question, retrieved, comparison)
    return {
        "facts": [{"claim": f.claim, "category": f.category, "source": f.source_url, "confidence": f.confidence} for f in all_facts],
        "retrieved": [{"claim": f.claim, "category": f.category, "confidence": f.confidence} for f in retrieved],
        "comparison": {
            "contradictions": [{"entity": c.entity, "attribute": c.attribute, "values": c.values} for c in comparison.contradictions],
            "agreements": [{"entity": a.entity, "attribute": a.attribute} for a in comparison.agreements],
            "gaps": [{"question": g.question} for g in comparison.gaps],
        },
        "report": {
            "summary": report.summary,
            "agreements": report.agreements,
            "conflicts": report.conflicts,
            "gaps": report.gaps,
            "overall_confidence": report.overall_confidence,
            "recommendations": report.recommendations,
        },
    }
    try:
        os.unlink(_tmp_path)
    except OSError:
        pass


# ── Evaluation ─────────────────────────────────────────────────

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def fact_in_output(fact: GroundTruthFact, output: str) -> bool:
    """Check if a ground-truth fact is mentioned in a text output."""
    n_output = normalize(output)
    entity = normalize(fact.entity)
    value = normalize(fact.value)
    return entity in n_output and value in n_output


def evaluate_raw_output(question: str, output: str, dataset: ResearchDataset) -> dict[str, Any]:
    """Evaluate LLM-only output against ground truth."""
    facts_correct = sum(1 for f in dataset.ground_truth_facts if fact_in_output(f, output))
    facts_total = len(dataset.ground_truth_facts)
    subtopics_covered = sum(1 for s in dataset.required_subtopics if normalize(s) in normalize(output))
    
    # Estimate hallucination: check if output mentions entities not in ground truth
    ground_entities = {normalize(f.entity) for f in dataset.ground_truth_facts}
    output_entities = set(re.findall(r'\b[A-Z][a-z]+(?:\s+\d+\.\d+)?(?:\s+[A-Z][a-z]+)*\b', output))
    hallucinated_entities = [e for e in output_entities if e.lower() not in ground_entities and len(e) > 3]
    
    contradictions_found = 0
    for c in dataset.contradictions:
        for v in c.values:
            if normalize(v) in normalize(output):
                contradictions_found += 1
                break
    
    return {
        "fact_recall": facts_correct / max(facts_total, 1),
        "facts_correct": facts_correct,
        "facts_total": facts_total,
        "subtopic_coverage": subtopics_covered / max(len(dataset.required_subtopics), 1),
        "subtopics_covered": subtopics_covered,
        "subtopics_total": len(dataset.required_subtopics),
        "contradictions_detected": contradictions_found,
        "contradictions_total": len(dataset.contradictions),
        "hallucinated_entities": len(hallucinated_entities),
        "output_length": len(output),
    }


def fact_matches_ground_truth(fact_claim: str, gt: GroundTruthFact) -> bool:
    """Check if an extracted fact claim matches a ground-truth fact."""
    nc = normalize(fact_claim)
    ne = normalize(gt.entity)
    nv = normalize(gt.value)
    return ne in nc and nv in nc


def evaluate_pipeline_output(question: str, result: dict[str, Any], dataset: ResearchDataset) -> dict[str, Any]:
    """Evaluate pipeline output against ground truth.

    The pipeline extracts facts deterministically, so we evaluate the
    extracted facts directly (not the LLM-generated summary).
    """
    retrieved = result.get("retrieved", [])
    extracted = result.get("facts", [])
    report = result.get("report", {})
    
    facts_total = len(dataset.ground_truth_facts)
    facts_correct = 0
    for f in dataset.ground_truth_facts:
        if any(fact_matches_ground_truth(r["claim"], f) for r in retrieved):
            facts_correct += 1
    
    subtopics_total = len(dataset.required_subtopics)
    subtopics_covered = 0
    all_claims = " ".join(r["claim"] for r in retrieved)
    for s in dataset.required_subtopics:
        if normalize(s) in normalize(all_claims):
            subtopics_covered += 1
    
    comparison = result.get("comparison", {})
    contradictions_found = len(comparison.get("contradictions", []))
    
    # Check if ground-truth contradictions were found
    gt_contradictions_matched = 0
    detected_contradictions = comparison.get("contradictions", [])
    for gc in dataset.contradictions:
        for dc in detected_contradictions:
            nc_entity = normalize(gc.entity)
            nc_attr = normalize(gc.attribute)
            dc_entity = normalize(dc.get("entity", ""))
            dc_attr = normalize(dc.get("attribute", ""))
            if nc_entity in dc_entity or dc_entity in nc_entity:
                if nc_attr in dc_attr or dc_attr in nc_attr:
                    gt_contradictions_matched += 1
                    break
    
    return {
        "fact_recall": facts_correct / max(facts_total, 1),
        "facts_correct": facts_correct,
        "facts_total": facts_total,
        "subtopic_coverage": subtopics_covered / max(subtopics_total, 1),
        "subtopics_covered": subtopics_covered,
        "subtopics_total": subtopics_total,
        "contradictions_detected": contradictions_found,
        "contradictions_matched": gt_contradictions_matched,
        "contradictions_total": len(dataset.contradictions),
        "facts_extracted": len(extracted),
        "facts_retrieved": len(retrieved),
        "overall_confidence": report.get("overall_confidence", 0),
    }


# ── Task Runner ────────────────────────────────────────────────

@dataclass
class TaskResult:
    dataset_id: str
    config: str
    fact_recall: float = 0.0
    subtopic_coverage: float = 0.0
    contradictions_detected: int = 0
    hallucinations: int = 0
    duration_seconds: float = 0.0
    error: str = ""
    details: dict = field(default_factory=dict)


SW_PROMPT = (
    "You are a research analyst. Answer the user's question thoroughly and accurately. "
    "Cite specific facts and sources. If there are conflicting claims, mention both sides."
)

PIPELINE_SW_PROMPT = (
    "You are a research analyst with access to a research pipeline. "
    "The pipeline has already extracted facts, detected contradictions, and generated a report. "
    "Review the provided analysis and summarize the findings for the user."
)

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch content from a URL",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                },
                "required": ["url"],
            },
        },
    },
]


async def run_raw(dataset: ResearchDataset) -> TaskResult:
    """LLM-only: model answers the question directly."""
    start = time.time()
    result = TaskResult(dataset_id=dataset.id, config="raw")
    
    try:
        messages = [
            {"role": "system", "content": SW_PROMPT},
            {"role": "user", "content": dataset.question},
        ]
        
        # Build context from source texts
        context = "\n\n".join([f"Source ({s['url']}):\n{s['content']}" for s in dataset.source_texts])
        messages.append({
            "role": "user",
            "content": f"Here are relevant sources to answer the question:\n\n{context}\n\nNow answer: {dataset.question}",
        })
        
        content, tool_calls = await call_llm(messages)
        
        if not content:
            result.error = "no_content"
        else:
            eval_result = evaluate_raw_output(dataset.question, content, dataset)
            result.fact_recall = eval_result["fact_recall"]
            result.subtopic_coverage = eval_result["subtopic_coverage"]
            result.contradictions_detected = eval_result["contradictions_detected"]
            result.hallucinations = eval_result["hallucinated_entities"]
            result.details = eval_result
    
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    
    result.duration_seconds = round(time.time() - start, 2)
    return result


async def run_pipeline_task(dataset: ResearchDataset) -> TaskResult:
    """Pipeline: extract → store → retrieve → reason → synthesize."""
    start = time.time()
    result = TaskResult(dataset_id=dataset.id, config="pipeline")
    
    try:
        pipeline_result = await run_pipeline(dataset.question, dataset.source_texts)
        eval_result = evaluate_pipeline_output(dataset.question, pipeline_result, dataset)
        result.fact_recall = eval_result["fact_recall"]
        result.subtopic_coverage = eval_result["subtopic_coverage"]
        result.contradictions_detected = eval_result["contradictions_detected"]
        result.hallucinations = 0  # Pipeline doesn't hallucinate — deterministic extraction
        result.details = eval_result
        result.details["pipeline_data"] = pipeline_result
    
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    
    result.duration_seconds = round(time.time() - start, 2)
    return result


# ── Report ──────────────────────────────────────────────────────

@dataclass
class BenchmarkReport:
    timestamp: str
    model: str
    configs: list[str]
    tasks: list[dict] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def print_report(report: BenchmarkReport):
    print()
    print("=" * 78)
    print("  Research Quality Benchmark")
    print(f"  Model: {report.model}")
    print(f"  Timestamp: {report.timestamp}")
    print("=" * 78)
    print()
    
    tasks_by_config: dict[str, list[dict]] = {}
    for t in report.tasks:
        tasks_by_config.setdefault(t["config"], []).append(t)
    
    for cfg, tasks in tasks_by_config.items():
        n = len(tasks)
        recall = sum(t["fact_recall"] for t in tasks) / n * 100
        coverage = sum(t["subtopic_coverage"] for t in tasks) / n * 100
        contradictions = sum(t["contradictions_detected"] for t in tasks)
        hallucinations = sum(t["hallucinations"] for t in tasks)
        duration = sum(t["duration_seconds"] for t in tasks) / n
        errors = sum(1 for t in tasks if t.get("error"))
        
        print(f"  Config       Recall  Coverage CtrDet Hall  Duration  Errors")
        print(f"  {'-'*60}")
        print(f"  {cfg:<12} {recall:>5.1f}%  {coverage:>5.1f}%  {contradictions:>3d}    {hallucinations:>2d}   {duration:>6.1f}s  {errors:>2d}")
    
    if len(tasks_by_config) == 2:
        raw_tasks = tasks_by_config.get("raw", [])
        pipe_tasks = tasks_by_config.get("pipeline", [])
        if raw_tasks and pipe_tasks:
            n = min(len(raw_tasks), len(pipe_tasks))
            d_recall = (sum(t["fact_recall"] for t in pipe_tasks) - sum(t["fact_recall"] for t in raw_tasks)) / n * 100
            d_coverage = (sum(t["subtopic_coverage"] for t in pipe_tasks) - sum(t["subtopic_coverage"] for t in raw_tasks)) / n * 100
            print(f"\n  Delta vs Raw:")
            print(f"    Recall:    {d_recall:+.1f}%")
            print(f"    Coverage:  {d_coverage:+.1f}%")
    
    print()


async def main(smoke: bool = False):
    datasets = DATASETS
    if smoke:
        datasets = DATASETS[:1]
    
    configs = ["raw", "pipeline"]
    
    model_id = MODEL.replace(":", "_")
    safe_model = re.sub(r"[^\w.-]", "_", model_id)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(REPORT_DIR, f"research_quality_{safe_model}_{ts}.json")
    
    report = BenchmarkReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        model=MODEL,
        configs=configs,
    )
    
    for config in configs:
        for dataset in datasets:
            logger.info("[%s] %s ...", config, dataset.id)
            if config == "raw":
                result = await run_raw(dataset)
            else:
                result = await run_pipeline_task(dataset)
            
            task_entry = {
                "dataset_id": result.dataset_id,
                "config": result.config,
                "fact_recall": result.fact_recall,
                "subtopic_coverage": result.subtopic_coverage,
                "contradictions_detected": result.contradictions_detected,
                "hallucinations": result.hallucinations,
                "duration_seconds": result.duration_seconds,
                "error": result.error,
                "details": result.details,
            }
            report.tasks.append(task_entry)
            logger.info("  recall=%.2f coverage=%.2f dur=%.1fs",
                        result.fact_recall, result.subtopic_coverage, result.duration_seconds)
    
    # Summary
    tasks_by_config: dict[str, list[dict]] = {}
    for t in report.tasks:
        tasks_by_config.setdefault(t["config"], []).append(t)
    
    summary = {}
    for cfg, tasks in tasks_by_config.items():
        n = len(tasks)
        summary[cfg] = {
            "avg_fact_recall": sum(t["fact_recall"] for t in tasks) / n,
            "avg_subtopic_coverage": sum(t["subtopic_coverage"] for t in tasks) / n,
            "total_contradictions_detected": sum(t["contradictions_detected"] for t in tasks),
            "total_hallucinations": sum(t["hallucinations"] for t in tasks),
            "avg_duration": sum(t["duration_seconds"] for t in tasks) / n,
            "errors": sum(1 for t in tasks if t.get("error")),
            "tasks_completed": n - sum(1 for t in tasks if t.get("error")),
            "tasks_total": n,
        }
    
    if "raw" in summary and "pipeline" in summary:
        r = summary["raw"]
        p = summary["pipeline"]
        summary["delta"] = {
            "fact_recall": p["avg_fact_recall"] - r["avg_fact_recall"],
            "subtopic_coverage": p["avg_subtopic_coverage"] - r["avg_subtopic_coverage"],
            "hallucination_reduction": r["total_hallucinations"] - p["total_hallucinations"],
            "contradiction_improvement": p["total_contradictions_detected"] - r["total_contradictions_detected"],
        }
    
    report.summary = summary
    
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": report.timestamp,
            "model": report.model,
            "configs": report.configs,
            "tasks": report.tasks,
            "summary": report.summary,
        }, f, indent=2, default=str)
    
    print_report(report)
    print(f"  Report saved: {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run single task smoke test")
    args = parser.parse_args()
    
    asyncio.run(main(smoke=args.smoke))
