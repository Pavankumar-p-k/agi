import re
from skills.utils import success_response, error_response

PATTERNS = {
    "email": r"[\w\.-]+@[\w\.-]+\.\w+",
    "url": r"https?://[\w./?-]+",
    "phone": r"\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}",
    "date": r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{2}-\d{2}-\d{4}",
    "ip address": r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
    "hex color": r"#[0-9a-fA-F]{3,8}",
    "number": r"-?\d+(?:\.\d+)?",
    "zip code": r"\d{5}(?:-\d{4})?",
    "uppercase": r"[A-Z]+",
    "lowercase": r"[a-z]+",
    "alpha": r"[A-Za-z]+",
    "alphanumeric": r"[A-Za-z0-9]+",
    "whitespace": r"\s+",
    "non-whitespace": r"\S+",
    "word boundary": r"\b\w+\b",
    "html tag": r"<[^>]+>",
    "time": r"\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?",
    "credit card": r"\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}",
    "uuid": r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    "filename": r"[\w,\s-]+\.\w+",
}

DESCRIPTION_TO_REGEX = {
    "match an email address": r"[\w\.-]+@[\w\.-]+\.\w+",
    "match a url": r"https?://[\w./?-]+",
    "match a phone number": r"\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}",
    "match a date": r"\d{4}-\d{2}-\d{2}",
    "match an ip address": r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
    "match numbers": r"-?\d+(?:\.\d+)?",
    "match a hex color": r"#[0-9a-fA-F]{3,8}",
    "match a zip code": r"\d{5}(?:-\d{4})?",
    "match html tags": r"<[^>]+>",
    "match whitespace": r"\s+",
    "match uppercase letters": r"[A-Z]+",
    "match lowercase letters": r"[a-z]+",
    "match a timestamp": r"\d{1,2}:\d{2}(?::\d{2})?",
    "match a uuid": r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    "match words": r"\b\w+\b",
    "match a filename": r"[\w,\s-]+\.\w+",
    "match a credit card": r"\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}",
}

EXPLANATIONS = {
    r"\d": "Matches any digit (0-9).",
    r"\w": "Matches any word character (letter, digit, underscore).",
    r"\s": "Matches any whitespace character (space, tab, newline).",
    r".": "Matches any character except newline.",
    r"*": "Matches zero or more of the preceding element.",
    r"+": "Matches one or more of the preceding element.",
    r"?": "Matches zero or one of the preceding element.",
    r"^": "Matches the start of a string.",
    r"$": "Matches the end of a string.",
    r"[]": "Character class; matches any character inside brackets.",
    r"[^]": "Negated character class; matches anything not in brackets.",
    r"|": "Alternation; matches either the pattern before or after.",
    r"()": "Grouping; captures the matched substring.",
    r"(?:)": "Non-capturing group.",
    r"(?=)": "Lookahead assertion.",
    r"(?!)": "Negative lookahead assertion.",
    r"\b": "Word boundary assertion.",
    r"\B": "Non-word boundary assertion.",
    r"{n}": "Exactly n occurrences.",
    r"{n,}": "n or more occurrences.",
    r"{n,m}": "Between n and m occurrences.",
}

def explain_regex(pattern: str) -> list:
    parts = []
    i = 0
    while i < len(pattern):
        if pattern[i] == '\\' and i + 1 < len(pattern):
            token = pattern[i:i+2]
            parts.append(EXPLANATIONS.get(token, f"Escape sequence: {token}"))
            i += 2
        elif pattern[i] in '.^$*+?|()[]{}':
            token = pattern[i]
            if token == '[' and i + 1 < len(pattern):
                end = pattern.find(']', i)
                if end != -1:
                    token = pattern[i:end+1]
                    parts.append(f"Character class: {token}")
                    i = end + 1
                    continue
            if token == '{':
                end = pattern.find('}', i)
                if end != -1:
                    token = pattern[i:end+1]
                    parts.append(EXPLANATIONS.get(token, f"Quantifier: {token}"))
                    i = end + 1
                    continue
            parts.append(EXPLANATIONS.get(token, f"Literal '{token}'"))
            i += 1
        else:
            parts.append(f"Literal '{pattern[i]}'")
            i += 1
    return parts

async def regex_helper(params: dict) -> dict:
    action = params.get("action", "").strip().lower()
    pattern = params.get("pattern", "").strip()
    description = params.get("description", "").strip()
    test_string = params.get("test_string", "")

    if action == "build":
        if not description:
            return error_response("Please provide a 'description' for building a regex.")
        desc_lower = description.lower().strip().rstrip(".")
        if desc_lower in DESCRIPTION_TO_REGEX:
            built = DESCRIPTION_TO_REGEX[desc_lower]
        else:
            for key, val in DESCRIPTION_TO_REGEX.items():
                if desc_lower in key or key in desc_lower:
                    built = val
                    break
            else:
                built = DESCRIPTION_TO_REGEX.get("match words", r"\b\w+\b")
        return success_response({
            "action": "build",
            "description": description,
            "pattern": built,
            "explanation": explain_regex(built)
        })

    elif action == "explain":
        if not pattern:
            return error_response("Please provide a 'pattern' to explain.")
        try:
            re.compile(pattern)
        except re.error as e:
            return error_response(f"Invalid regex pattern: {e}")
        return success_response({
            "action": "explain",
            "pattern": pattern,
            "explanation": explain_regex(pattern)
        })

    elif action == "test":
        if not pattern:
            return error_response("Please provide a 'pattern' to test.")
        try:
            compiled = re.compile(pattern)
        except re.error as e:
            return error_response(f"Invalid regex pattern: {e}")
        matches = compiled.findall(str(test_string))
        return success_response({
            "action": "test",
            "pattern": pattern,
            "test_string": test_string,
            "matches": matches,
            "match_count": len(matches),
            "full_match": bool(compiled.fullmatch(str(test_string)))
        })

    else:
        return error_response("Action must be 'build', 'explain', or 'test'.")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
