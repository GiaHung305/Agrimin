"""Deterministic Vietnamese intent checks for time-sensitive answers."""

from __future__ import annotations

import re
from typing import Literal

from app.retrieval.text_normalization import normalize_vietnamese

_ACCENTED_WEATHER_PATTERN = re.compile(
    r"\b(?:thời tiết|mưa|nắng|nhiệt độ|độ ẩm|bão|gió|"
    r"dự báo (?:thời tiết|mưa|nắng|bão))\b",
    re.IGNORECASE,
)
_NORMALIZED_WEATHER_PATTERN = re.compile(
    r"\b(?:thoi tiet|du bao (?:thoi tiet|mua|nang|bao)|"
    r"nhiet do|do am|co mua|troi mua|mua (?:khong|lon|nho|rao)|"
    r"luong mua|co nang|troi nang|nang nong|"
    r"bao so(?: [0-9]+)?|con bao|bao do bo|gio giat|toc do gio)\b"
)
_TEMPORAL_PATTERN = re.compile(
    r"\b(?:hom nay|hom qua|hien tai|bay gio|sang nay|chieu nay|toi nay|"
    r"ngay mai|tuan nay|tuan toi|thang nay|nam nay|mua nay|"
    r"moi nhat|moi day|gan day|vua xay ra)\b"
)
_AGRICULTURAL_WEATHER_DECISION_PATTERN = re.compile(
    r"\b(?:anh huong|benh|bon|canh tac|cay|che pham|dat trong|dich hai|"
    r"giai doan|gieo|giong|lieu|mua vu|nam benh|nong do|nong trai|"
    r"phan bon|pha|phun|ruong|sau|sinh truong|thu hoach|thuoc|trong|"
    r"tuoi|vuon|xuong giong)\b"
)
_CASUAL_PATTERNS: tuple[
    tuple[Literal["greeting", "thanks", "acknowledgement"], re.Pattern[str]],
    ...,
] = (
    (
        "greeting",
        re.compile(r"^(?:xin chao|chao(?: ban| agrimind)?|hello|hi|alo)$"),
    ),
    (
        "thanks",
        re.compile(
            r"^(?:cam on(?: ban| agrimind)?(?: nhe)?|thank you|thanks)$"
        ),
    ),
    (
        "acknowledgement",
        re.compile(r"^(?:ok|okay|duoc roi|hieu roi|ro roi|dong y|tot)$"),
    ),
)


def _normalized_question(question: str) -> str:
    return " ".join(normalize_vietnamese(question).split())


def has_weather_intent(question: str) -> bool:
    """Recognize weather intent without confusing unaccented homonyms."""
    return bool(
        _ACCENTED_WEATHER_PATTERN.search(question)
        or _NORMALIZED_WEATHER_PATTERN.search(_normalized_question(question))
    )


def is_weather_only_question(question: str) -> bool:
    """Separate direct forecasts from weather-informed farming decisions."""
    normalized = _normalized_question(question)
    return has_weather_intent(question) and not bool(
        _AGRICULTURAL_WEATHER_DECISION_PATTERN.search(normalized)
    )


def casual_message_kind(
    question: str,
) -> Literal["greeting", "thanks", "acknowledgement"] | None:
    """Recognize only complete, low-risk social turns."""
    normalized = re.sub(r"[^a-z0-9 ]+", " ", _normalized_question(question))
    normalized = " ".join(normalized.split())
    for kind, pattern in _CASUAL_PATTERNS:
        if pattern.fullmatch(normalized):
            return kind
    return None


def is_realtime_sensitive_question(question: str) -> bool:
    """Return true when a cached answer could be stale because time matters."""
    normalized = _normalized_question(question)
    return has_weather_intent(question) or bool(_TEMPORAL_PATTERN.search(normalized))
