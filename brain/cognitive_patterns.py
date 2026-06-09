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

"""brain/cognitive_patterns.py
10 cognitive patterns — each calls ReasoningEngine.reason() with a tuned system prompt.
All return the same dict shape: {conclusion, trace, confidence, model_group}

Usage:
    from brain.cognitive_patterns import plan, critique, evaluate
    result = await plan("Build a restaurant website")
    print(result["conclusion"])
"""

from __future__ import annotations

from brain.reasoning_engine import reasoning_engine


def _wrap(result):
    return result.to_dict()


async def plan(goal: str, context: str = "") -> dict:
    """Break a goal into concrete, ordered steps with dependencies."""
    return _wrap(await reasoning_engine.reason(
        goal,
        context,
        system_override=(
            "You are a planning expert. Break goals into concrete, ordered steps. "
            "Identify dependencies between steps. Estimate effort for each step. "
            "Think in <think> tags, output the plan in <answer> tags."
        ),
    ))


async def critique(output: str, context: str = "") -> dict:
    """Find logical flaws, missing edge cases, and assumptions."""
    return _wrap(await reasoning_engine.reason(
        f"Critique this output:\n\n{output}",
        context,
        system_override=(
            "You are a critical reviewer. Find logical flaws, missing edge cases, "
            "hidden assumptions, and potential failure modes. Be constructive. "
            "Think in <think> tags, output your critique in <answer> tags."
        ),
    ))


async def reflect(conversation: str, context: str = "") -> dict:
    """Extract lessons learned and improvement suggestions from an interaction."""
    return _wrap(await reasoning_engine.reason(
        f"Reflect on this conversation:\n\n{conversation}",
        context,
        system_override=(
            "You are a reflective learner. What was learned? What worked well? "
            "What should change next time? Think in <think> tags, "
            "output your reflection in <answer> tags."
        ),
    ))


async def verify(claim: str, evidence: str, context: str = "") -> dict:
    """Check if a claim is supported by the given evidence."""
    return _wrap(await reasoning_engine.reason(
        f"Claim: {claim}\n\nEvidence:\n{evidence}",
        context,
        system_override=(
            "You are a fact-checker. Does the evidence support the claim? "
            "Rate your confidence 1-10. Explain your reasoning step by step. "
            "Think in <think> tags, output verdict in <answer> tags."
        ),
    ))


async def simulate(scenario: str, context: str = "") -> dict:
    """Run a what-if analysis on a given scenario."""
    return _wrap(await reasoning_engine.reason(
        f"Scenario:\n{scenario}",
        context,
        system_override=(
            "You are a simulation engine. Walk through what happens step by step. "
            "Consider best case, worst case, and most likely outcomes. "
            "Think in <think> tags, output simulation results in <answer> tags."
        ),
    ))


async def prioritize(options: str, criteria: str = "impact vs effort", context: str = "") -> dict:
    """Rank options by specified criteria."""
    return _wrap(await reasoning_engine.reason(
        f"Options:\n{options}\n\nCriteria: {criteria}",
        context,
        system_override=(
            "You are a decision analyst. Rank each option by the given criteria. "
            "Explain your ranking rationale. Recommend the top choice. "
            "Think in <think> tags, output ranked list in <answer> tags."
        ),
    ))


async def decompose(problem: str, context: str = "") -> dict:
    """Split a complex problem into independent sub-problems."""
    return _wrap(await reasoning_engine.reason(
        f"Problem:\n{problem}",
        context,
        system_override=(
            "You are a problem decomposition specialist. Break this problem into "
            "independent sub-problems that can be solved in parallel. "
            "Identify inputs and outputs between sub-problems. "
            "Think in <think> tags, output the decomposition in <answer> tags."
        ),
    ))


async def synthesize(sources: str, context: str = "") -> dict:
    """Combine multiple sources into a coherent, non-redundant summary."""
    return _wrap(await reasoning_engine.reason(
        f"Sources:\n{sources}",
        context,
        system_override=(
            "You are a synthesis expert. Combine these sources into a coherent, "
            "non-redundant summary. Resolve contradictions. Identify consensus. "
            "Think in <think> tags, output synthesized summary in <answer> tags."
        ),
    ))


async def hypothesize(observation: str, context: str = "") -> dict:
    """Generate explanations for a given observation (debugging/diagnosis)."""
    return _wrap(await reasoning_engine.reason(
        f"Observation:\n{observation}",
        context,
        system_override=(
            "You are a diagnostic expert. Given this observation, generate plausible "
            "hypotheses. Rank them by likelihood. Suggest how to test each one. "
            "Think in <think> tags, output hypotheses in <answer> tags."
        ),
    ))


async def evaluate(output: str, criteria: str, context: str = "") -> dict:
    """Score output against explicit quality criteria."""
    return _wrap(await reasoning_engine.reason(
        f"Output to evaluate:\n{output}\n\nEvaluation criteria:\n{criteria}",
        context,
        system_override=(
            "You are a quality evaluator. Score the output against each criterion "
            "on a scale of 1-10. Provide justification for each score. "
            "Output a JSON object with scores and overall verdict in <answer> tags. "
            "Think in <think> tags, output JSON in <answer> tags."
        ),
    ))


PATTERNS = {
    "plan": plan,
    "critique": critique,
    "reflect": reflect,
    "verify": verify,
    "simulate": simulate,
    "prioritize": prioritize,
    "decompose": decompose,
    "synthesize": synthesize,
    "hypothesize": hypothesize,
    "evaluate": evaluate,
}


class CognitivePatterns:
    """Class wrapper around module-level pattern functions for UnifiedBrain."""

    async def plan(self, goal: str, context: str = "") -> dict:
        return await plan(goal, context)

    async def critique(self, output: str, context: str = "") -> dict:
        return await critique(output, context)

    async def reflect(self, conversation: str, context: str = "") -> dict:
        return await reflect(conversation, context)

    async def verify(self, claim: str, evidence: str, context: str = "") -> dict:
        return await verify(claim, evidence, context)

    async def simulate(self, scenario: str, context: str = "") -> dict:
        return await simulate(scenario, context)

    async def prioritize(self, options: str, criteria: str = "impact vs effort", context: str = "") -> dict:
        return await prioritize(options, criteria, context)

    async def decompose(self, problem: str, context: str = "") -> dict:
        return await decompose(problem, context)

    async def synthesize(self, sources: str, context: str = "") -> dict:
        return await synthesize(sources, context)

    async def hypothesize(self, observation: str, context: str = "") -> dict:
        return await hypothesize(observation, context)

    async def evaluate(self, output: str, criteria: str, context: str = "") -> dict:
        return await evaluate(output, criteria, context)


cognitive_patterns = CognitivePatterns()
