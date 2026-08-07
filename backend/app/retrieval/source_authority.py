"""Controlled source taxonomy for evidence and high-risk safety policy."""

from __future__ import annotations

from enum import StrEnum


class SourceType(StrEnum):
    GOVERNMENT = "government"
    EXTENSION = "extension"
    INTERNATIONAL = "international_organization"
    MANUFACTURER_LABEL = "manufacturer_label"
    RESEARCH = "research"
    USER_UPLOAD = "user_upload"
    UNKNOWN = "unknown"


_AUTHORITY_SCORES = {
    SourceType.GOVERNMENT: 0.95,
    SourceType.EXTENSION: 0.90,
    SourceType.INTERNATIONAL: 0.90,
    SourceType.MANUFACTURER_LABEL: 0.90,
    SourceType.RESEARCH: 0.80,
    SourceType.USER_UPLOAD: 0.40,
    SourceType.UNKNOWN: 0.20,
}

_DOSAGE_SOURCE_TYPES = {
    SourceType.GOVERNMENT,
    SourceType.EXTENSION,
    SourceType.INTERNATIONAL,
    SourceType.MANUFACTURER_LABEL,
}


def normalize_source_type(value: str | SourceType | None) -> SourceType:
    try:
        return SourceType(str(value or SourceType.UNKNOWN.value))
    except ValueError:
        return SourceType.UNKNOWN


def authority_score(value: str | SourceType | None) -> float:
    return _AUTHORITY_SCORES[normalize_source_type(value)]


def supports_high_risk(value: str | SourceType | None) -> bool:
    return authority_score(value) >= 0.80


def supports_numeric_dosage(value: str | SourceType | None) -> bool:
    return normalize_source_type(value) in _DOSAGE_SOURCE_TYPES
