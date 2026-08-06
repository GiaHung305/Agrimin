import re
import unicodedata

# The input is normalised before matching, preventing simple case, spacing,
# accent and zero-width-character variants from bypassing this first line of
# defence. This is intentionally conservative and complements, rather than
# replaces, prompt hardening in the workflow itself.
INJECTION_PATTERNS = [
    r"\b(?:ignore|disregard|forget)\b.*\b(?:previous|above|prior)\b.*\b(?:instructions?|rules?|prompt)\b",
    r"\b(?:bo qua|quen)\b.*\b(?:huong dan|chi dan|quy tac|prompt)\b",
    r"\byou\s+are\s+now\b",
    r"\bban\s+bay\s+gio\s+la\b",
    r"\b(?:reveal|show|print|extract|tiet lo|hien thi)\b.*\b(?:system|developer)\b.*\b(?:prompt|instructions?)\b",
    r"\b(?:jailbreak|dan\s+mode)\b",
    r"\bact\s+as\s+(?:if\s+you\s+are\s+)?(?:a\s+)?(?:different|new)\s+ai\b",
]

_compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in INJECTION_PATTERNS]


def _normalise_for_security_check(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Cf")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).casefold().strip()


def contains_prompt_injection(text: str) -> bool:
    """Return whether text matches a common prompt-injection pattern."""
    normalised_text = _normalise_for_security_check(text)
    return any(pattern.search(normalised_text) for pattern in _compiled_patterns)
