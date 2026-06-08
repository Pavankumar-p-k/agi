import re
from skills.utils import success_response, error_response

STOP_PHRASES = [
    "this paper", "in this paper", "we present", "we propose", "we introduce",
    "this study", "this research", "in this study", "our approach", "our method",
    "we show", "we demonstrate", "we find", "we report", "the authors",
    "abstract", "introduction", "methodology", "methods", "results",
    "discussion", "conclusion", "references",
]

def extract_sentences(text: str) -> list:
    text = re.sub(r'\s+', ' ', text)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if len(s.strip()) > 20]

def get_key_sentences(text: str, count: int = 5) -> list:
    sentences = extract_sentences(text)
    if len(sentences) <= count:
        return sentences

    scored = []
    for s in sentences:
        score = 0
        s_lower = s.lower()
        if any(phrase in s_lower for phrase in ["result", "find", "show", "demonstrate", "conclude", "therefore", "thus", "however", "significant", "important", "key", "novel", "method", "approach", "propose", "develop", "experiment", "accuracy", "improve", "achieve", "perform"]):
            score += 2
        if s_lower.startswith(("we", "our", "the", "this")):
            score += 1
        if len(s.split()) > 15:
            score += 1
        scored.append((score, s))

    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:count]]

def extract_methodology(text: str) -> str:
    sentences = extract_sentences(text)
    method_sentences = []
    capture = False
    for s in sentences:
        s_lower = s.lower()
        if any(phrase in s_lower for phrase in ["method", "approach", "we propose", "we introduce", "we develop", "we present", "our system", "our model", "architecture", "algorithm", "implementation"]):
            capture = True
        if capture:
            method_sentences.append(s)
        if any(phrase in s_lower for phrase in ["result", "experiment", "evaluation", "discussion"]) and len(method_sentences) > 3:
            break
    return " ".join(method_sentences[:5]) if method_sentences else "Not explicitly identified."

def extract_results(text: str) -> str:
    sentences = extract_sentences(text)
    result_sentences = []
    capture = False
    for s in sentences:
        s_lower = s.lower()
        if any(phrase in s_lower for phrase in ["result", "experiment", "evaluation", "find", "show", "achieve", "outperform", "accuracy"]):
            capture = True
        if capture:
            result_sentences.append(s)
        if any(phrase in s_lower for phrase in ["discussion", "conclusion", "future work"]):
            break
    return " ".join(result_sentences[:5]) if result_sentences else "Not explicitly identified."

def extract_conclusion(text: str) -> str:
    sentences = extract_sentences(text)
    conclusion_sentences = []
    capture = False
    for s in sentences:
        s_lower = s.lower()
        if any(phrase in s_lower for phrase in ["conclusion", "conclude", "summary", "finally", "we have shown", "we have demonstrated"]) and not capture:
            capture = True
        if capture:
            conclusion_sentences.append(s)
    return " ".join(conclusion_sentences[:3]) if conclusion_sentences else "Not explicitly identified."

async def paper_summarizer(params: dict) -> dict:
    text = params.get("text", "").strip()
    style = params.get("style", "brief").strip().lower()
    max_length = params.get("max_length", None)

    if not text:
        return error_response("Please provide 'text' to summarize.")
    if len(text) < 50:
        return error_response("Text is too short to summarize (min 50 characters).")

    if style not in ("brief", "detailed", "bullet-points"):
        style = "brief"

    key_sentences = get_key_sentences(text, 5)
    methodology = extract_methodology(text)
    results = extract_results(text)
    conclusion = extract_conclusion(text)

    brief = " ".join(key_sentences[:3])
    if max_length and len(brief) > max_length:
        brief = brief[:max_length].rsplit(" ", 1)[0] + "."

    if style == "brief":
        if max_length and len(brief) > max_length:
            brief = brief[:max_length].rsplit(" ", 1)[0] + "."
        summary = brief
    elif style == "detailed":
        parts = [
            f"Methodology: {methodology}",
            f"Results: {results}",
            f"Conclusion: {conclusion}",
        ]
        summary = "\n\n".join(parts)
        if max_length and len(summary) > max_length:
            summary = summary[:max_length].rsplit(" ", 1)[0] + "."
    else:
        bullets = [f"- {s}" for s in key_sentences]
        summary = "\n".join(bullets)
        if max_length and len(summary) > max_length:
            summary = summary[:max_length].rsplit("\n", 1)[0]

    return success_response({
        "summary": summary,
        "style": style,
        "key_points": key_sentences,
        "methodology": methodology,
        "results": results,
        "conclusion": conclusion,
        "sentence_count": len(extract_sentences(text))
    })

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
