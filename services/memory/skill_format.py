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
