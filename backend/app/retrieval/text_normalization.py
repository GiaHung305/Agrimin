"""Vietnamese-aware lexical normalization for sparse retrieval."""

from __future__ import annotations

import re
import unicodedata

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)?%?")


def normalize_vietnamese(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    return without_marks.replace("đ", "d")


def tokenize_vietnamese(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(normalize_vietnamese(text))
