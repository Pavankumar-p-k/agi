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

import re
import unicodedata


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


class Skill:
    def __init__(self, **kwargs):
        self.name: str = kwargs.get("name", "")
        self.description: str = kwargs.get("description", "")
        self.version: str = kwargs.get("version", "1.0.0")
        self.category: str = kwargs.get("category", "general")
        self.tags: list = kwargs.get("tags") or []
        self.platforms: list = kwargs.get("platforms") or []
        self.requires_toolsets: list = kwargs.get("requires_toolsets") or []
        self.fallback_for_toolsets: list = kwargs.get("fallback_for_toolsets") or []
        self.status: str = kwargs.get("status", "draft")
        self.confidence: float = kwargs.get("confidence", 0.8)
        self.source: str = kwargs.get("source", "learned")
        self.teacher_model: str = kwargs.get("teacher_model", "")
        self.owner: str = kwargs.get("owner", "")
        self.when_to_use: str = kwargs.get("when_to_use", "")
        self.procedure: list = kwargs.get("procedure") or kwargs.get("steps") or []
        self.pitfalls: list = kwargs.get("pitfalls") or []
        self.verification: list = kwargs.get("verification") or []
        self.body_extra: str = kwargs.get("body_extra", "")
        self.title: str = kwargs.get("title", "")
        self.problem: str = kwargs.get("problem", "")
        self.solution: str = kwargs.get("solution", "")
        self.steps: list = kwargs.get("steps") or []

    @classmethod
    def from_markdown(cls, md: str) -> Skill:
        lines = md.split("\n")
        kwargs = {}
        header = ""
        body = []
        in_frontmatter = False
        frontmatter_lines = []
        for line in lines:
            if line.strip() == "---" and not in_frontmatter:
                in_frontmatter = True
                continue
            if line.strip() == "---" and in_frontmatter:
                in_frontmatter = False
                continue
            if in_frontmatter:
                frontmatter_lines.append(line)
                continue
            if not in_frontmatter and not frontmatter_lines and line.startswith("# "):
                header = line[2:].strip()
            elif not in_frontmatter:
                body.append(line)

        for fl in frontmatter_lines:
            if ":" in fl:
                key, _, val = fl.partition(":")
                kwargs[key.strip()] = val.strip()

        if not kwargs.get("name") and header:
            kwargs["name"] = slugify(header)
        if not kwargs.get("description") and header:
            kwargs["description"] = header
        if body:
            body_text = "\n".join(body).strip()
            kwargs["body_extra"] = body_text
            if not kwargs.get("procedure"):
                steps = [b for b in body if b.strip().startswith("- ") or b.strip().startswith("* ")]
                if steps:
                    kwargs["procedure"] = [s.strip("- *") for s in steps]

        return cls(**kwargs)
