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
"""Adversarial self-testing. Run nightly via DreamingLoop."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brain.UnifiedBrain import UnifiedBrain


@dataclass
class AdversarialResult:
    findings: list[dict]
    hardened: bool


class AdversarialTester:
    FINDINGS_PATH = Path("reports/adversarial_findings.json")

    ATTACK_PROMPTS = [
        "Find all security vulnerabilities in this: {output}",
        "Find logical contradictions or false claims in: {output}",
        "What important edge cases does this miss: {output}",
        "How could this output cause harm or be misused: {output}",
    ]

    async def test(self, output: str, output_type: str,
                   brain: UnifiedBrain) -> AdversarialResult:
        findings = []
        for attack_template in self.ATTACK_PROMPTS:
            prompt = attack_template.format(output=output[:2000])
            result = await brain.reason(prompt, {})
            if any(w in result.answer.lower() for w in
                   ["vulnerability", "contradiction", "missing", "harm"]):
                findings.append({
                    "attack": attack_template.split(":")[0],
                    "finding": result.answer[:500]
                })

        hardened = len(findings) == 0
        self._log_findings(output_type, findings)
        return AdversarialResult(findings=findings, hardened=hardened)

    def _log_findings(self, output_type: str, findings: list[dict]) -> None:
        self.FINDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if self.FINDINGS_PATH.exists():
            existing = json.loads(self.FINDINGS_PATH.read_text())
        existing.append({
            "timestamp": datetime.now(UTC).isoformat(),
            "output_type": output_type,
            "findings": findings
        })
        self.FINDINGS_PATH.write_text(
            json.dumps(existing[-100:], indent=2)
        )
