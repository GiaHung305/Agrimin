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

# Match accent-sensitive phrases before diacritic folding. In Vietnamese,
# ``ẩn`` would otherwise collapse to ``an`` and could falsely match ordinary
# wording such as ``hướng dẫn an toàn``.
_ACCENT_SENSITIVE_INJECTION_PATTERNS = [
    re.compile(
        r"\b(?:làm theo|tuân theo|ưu tiên|thực hiện)\b.{0,80}"
        r"\b(?:hướng dẫn|chỉ dẫn|mệnh lệnh)\s+(?:ẩn|bí mật|nội bộ)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:follow|obey|prioritize)\b.{0,80}"
        r"\b(?:hidden|secret|internal)\s+(?:instructions?|rules?|prompt)\b",
        re.IGNORECASE,
    ),
]
_HIDDEN_INSTRUCTION_OVERRIDE_PATTERN = re.compile(
    r"\b(?:bỏ qua|thay cho|ghi đè|vô hiệu hóa|tiết lộ|hiển thị|"
    r"ignore|replace|override|disable|reveal|show)\b.{0,100}"
    r"\b(?:quy tắc|an toàn|prompt|hệ thống|instructions?|rules?|safety|system)\b"
    r"|\b(?:quy tắc|an toàn|prompt|hệ thống|instructions?|rules?|safety|system)\b"
    r".{0,100}\b(?:bỏ qua|thay cho|ghi đè|vô hiệu hóa|tiết lộ|hiển thị|"
    r"ignore|replace|override|disable|reveal|show)\b",
    re.IGNORECASE,
)


def _normalise_for_security_check(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Cf")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).casefold().strip()


def contains_prompt_injection(text: str) -> bool:
    """Return whether text matches a common prompt-injection pattern."""
    visible_text = unicodedata.normalize("NFKC", text)
    visible_text = "".join(
        char for char in visible_text if unicodedata.category(char) != "Cf"
    )
    has_hidden_instruction = any(
        pattern.search(visible_text)
        for pattern in _ACCENT_SENSITIVE_INJECTION_PATTERNS
    )
    if has_hidden_instruction and _HIDDEN_INSTRUCTION_OVERRIDE_PATTERN.search(
        visible_text
    ):
        return True
    normalised_text = _normalise_for_security_check(text)
    return any(pattern.search(normalised_text) for pattern in _compiled_patterns)
