"""Shared normalization for deterministic workflow text matching."""

import unicodedata


def normalize_workflow_text(value: str) -> str:
    """Normalize Vietnamese text without changing word-boundary semantics."""
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return " ".join(normalized.split())
