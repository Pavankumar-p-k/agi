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
"""core/failure_classifier.py
Categorizes build failures so the system can pick the right remediation strategy.
"""
import logging
import re
from enum import Enum

logger = logging.getLogger(__name__)


class FailureCategory(Enum):
    TRANSIENT = "transient"
    LOGIC = "logic"
    RESOURCE = "resource"
    TOOL = "tool"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


FAILURE_PATTERNS: dict[str, list[tuple[str, FailureCategory]]] = {
    "transient": [
        (r"(?i)\b(timeout|timed?\s*out|connection\s*(refused|reset|closed|error))\b", FailureCategory.TRANSIENT),
        (r"(?i)\b(429|rate\s*limit|too\s*many\s*requests|quota\s*exceeded)\b", FailureCategory.TRANSIENT),
        (r"(?i)\b(retry\s*after|try\s*again\s*later|temporarily\s*unavailable)\b", FailureCategory.TRANSIENT),
        (r"(?i)\b(503|502|504|service\s*unavailable|bad\s*gateway)\b", FailureCategory.TRANSIENT),
        (r"(?i)\b(network\s*(error|issue|unreachable)|dns\s*lookup\s*failed)\b", FailureCategory.TRANSIENT),
        (r"(?i)\b(ECONNREFUSED|ECONNRESET|ETIMEDOUT|ENETUNREACH)\b", FailureCategory.TRANSIENT),
    ],
    "logic": [
        (r"(?i)\b(wrong\s*(plan|approach|strategy|logic|direction)|incorrect\s*(reasoning|logic))\b", FailureCategory.LOGIC),
        (r"(?i)\b(doesn't\s*make\s*sense|not\s*what\s*was\s*asked|misunderstood)\b", FailureCategory.LOGIC),
        (r"(?i)\b(fix\s*(the\s*)?wrong|broke\s*something|regression)\b", FailureCategory.LOGIC),
        (r"(?i)\b(missing\s*(feature|logic|requirement)|incomplete\s*implementation)\b", FailureCategory.LOGIC),
    ],
    "resource": [
        (r"(?i)\b(no\s*such\s*file|file\s*not\s*found|FileNotFoundError|ENOENT)\b", FailureCategory.RESOURCE),
        (r"(?i)\b(missing\s*(API|api)\s*key|no\s*API\s*key|api_key_not_found)\b", FailureCategory.RESOURCE),
        (r"(?i)\b(template\s*not\s*found|module\s*not\s*found|ImportError|ModuleNotFoundError)\b", FailureCategory.RESOURCE),
        (r"(?i)\b(permission\s*denied|access\s*denied|EACCES|EPERM)\b", FailureCategory.RESOURCE),
        (r"(?i)\b(disk\s*full|no\s*space\s*left|ENOSPC)\b", FailureCategory.RESOURCE),
        (r"(?i)\b(directory\s*not\s*found|path\s*not\s*found|not\s*a\s*directory)\b", FailureCategory.RESOURCE),
    ],
    "tool": [
        (r"(?i)\b(command\s*not\s*found|not\s*installed|unknown\s*command)\b", FailureCategory.TOOL),
        (r"(?i)\b(agent\s*error|tool\s*failed|subprocess\s*(error|failed|crashed))\b", FailureCategory.TOOL),
        (r"(?i)\b(exit\s*code\s*[1-9]|non.?zero\s*exit|crashed|segmentation\s*fault)\b", FailureCategory.TOOL),
        (r"(?i)\b(pip\s*(error|failed)|npm\s*ERR|yarn\s*error|gradle\s*build\s*failed)\b", FailureCategory.TOOL),
        (r"(?i)\b(not\s*a\s*valid\s*command|unrecognized\s*argument|usage:)\b", FailureCategory.TOOL),
    ],
    "validation": [
        (r"(?i)\b(validation\s*failed|check\s*failed|assertion\s*error)\b", FailureCategory.VALIDATION),
        (r"(?i)\b(test\s*failed|test\s*error|unit\s*test|pytest\s*(error|failure))\b", FailureCategory.VALIDATION),
        (r"(?i)\b(syntax\s*error|parse\s*error|compilation\s*error|build\s*failed)\b", FailureCategory.VALIDATION),
        (r"(?i)\b(lint(ing)?\s*(error|failed)|style\s*(error|violation)|PEP\s*8)\b", FailureCategory.VALIDATION),
        (r"(?i)\b(type\s*(error|mismatch)|TypeError|ValueError|KeyError|AttributeError)\b", FailureCategory.VALIDATION),
        (r"(?i)\b(does\s*not\s*pass|fails?\s*validation|invalid\s*(input|output|config))\b", FailureCategory.VALIDATION),
    ],
}

FAILURE_PATTERNS_FLAT: list[tuple[re.Pattern, FailureCategory]] = []
for category, patterns in FAILURE_PATTERNS.items():
    for pattern_str, cat in patterns:
        FAILURE_PATTERNS_FLAT.append((re.compile(pattern_str), cat))


REMEDIATION_MAP = {
    FailureCategory.TRANSIENT: "Retry the operation with exponential backoff. Consider adding jitter and increasing timeout.",
    FailureCategory.LOGIC: "Replan the approach. Review the goal requirements and generate a new task plan.",
    FailureCategory.RESOURCE: "Resolve the missing resource. Check file paths, API keys, and dependencies.",
    FailureCategory.TOOL: "Switch to a different agent or tool. The current one is failing or unavailable.",
    FailureCategory.VALIDATION: "Generate targeted fix tasks to address the specific validation checks that failed.",
    FailureCategory.UNKNOWN: "Review the failure manually. Consider running diagnostics and checking logs.",
}


class FailureClassifier:
    def classify(self, failure_text: str, context: dict = None) -> FailureCategory:
        if not failure_text:
            return FailureCategory.UNKNOWN

        for pattern, category in FAILURE_PATTERNS_FLAT:
            if pattern.search(failure_text):
                logger.debug(f"[CLASSIFIER] {category.value}: {pattern.pattern}")
                return category

        if context:
            tool_name = context.get("tool", "")
            if tool_name and tool_name in failure_text.lower():
                return FailureCategory.TOOL
            if "config" in context and not context["config"]:
                return FailureCategory.RESOURCE

        return FailureCategory.UNKNOWN

    @staticmethod
    def get_remediation(category: FailureCategory) -> str:
        return REMEDIATION_MAP.get(category, REMEDIATION_MAP[FailureCategory.UNKNOWN])


_classifier = FailureClassifier()


def classify(failure_text: str, context: dict = None) -> FailureCategory:
    return _classifier.classify(failure_text, context)
