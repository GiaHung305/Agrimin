"""Canonical extraction of numeric agricultural measurements and dilution ratios."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


_NUMBER = r"\d+(?:[.,]\d+)?"
_UNIT = r"lít|lit|gram|gam|ml|cc|mg|kg|ppm|m²|m2|ha|g|l|%"
_DENOMINATOR = r"lít|lit|bình|binh|cây|cay|m²|m2|ha|kg|g|l"
_MEASUREMENT_PATTERN = re.compile(
    rf"(?<!\w)({_NUMBER})\s*({_UNIT})"
    rf"(?:\s*(?:/|mỗi|moi)\s*({_DENOMINATOR}))?(?!\w)",
    re.IGNORECASE,
)
_DILUTION_RATIO_PATTERN = re.compile(
    rf"(?<!\w)({_NUMBER})\s*:\s*({_NUMBER})(?!\w)"
)
_UNIT_ALIASES = {
    "bình": "tank",
    "binh": "tank",
    "cây": "plant",
    "cay": "plant",
    "cc": "ml",
    "gam": "g",
    "gram": "g",
    "lit": "l",
    "lít": "l",
    "m²": "m2",
}


def _normalized_number(value: str) -> str:
    try:
        number = Decimal(value.replace(",", ".")).normalize()
    except InvalidOperation:
        return value
    return format(number, "f")


def _normalized_unit(value: str) -> str:
    unit = value.casefold()
    return _UNIT_ALIASES.get(unit, unit)


def extract_numeric_measurements(text: str | None) -> set[tuple[str, str]]:
    """Return exact values with canonical units, rates, and dilution ratios."""
    claims: set[tuple[str, str]] = set()
    for value, unit, denominator in _MEASUREMENT_PATTERN.findall(text or ""):
        normalized_unit = _normalized_unit(unit)
        if denominator:
            normalized_unit = (
                f"{normalized_unit}/{_normalized_unit(denominator)}"
            )
        claims.add((_normalized_number(value), normalized_unit))
    for numerator, denominator in _DILUTION_RATIO_PATTERN.findall(text or ""):
        claims.add(
            (
                f"{_normalized_number(numerator)}:"
                f"{_normalized_number(denominator)}",
                "ratio",
            )
        )
    return claims
