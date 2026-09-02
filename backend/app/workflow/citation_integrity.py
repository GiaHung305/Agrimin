"""Deterministic checks that keep technical claims locally cited."""

from __future__ import annotations

import re

from app.retrieval.text_normalization import normalize_vietnamese


_CITATION_MARKER_PATTERN = re.compile(r"\[E(\d+)\]", re.IGNORECASE)
_MARKER_ONLY_PATTERN = re.compile(r"^(?:\s*\[E\d+\]\s*)+$", re.IGNORECASE)
_MARKDOWN_PREFIX_PATTERN = re.compile(r"^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+)")
_TECHNICAL_PATTERN = re.compile(
    r"\b(?:"
    r"benh|sau benh|nam|vi khuan|virus|trieu chung|dau hieu|nguyen nhan|"
    r"gia thuyet|chan doan|phong tru|dieu tri|xu ly|"
    r"bon|phan bon|dam|lan|kali|phun|tuoi|tia canh|thoat nuoc|luan canh|"
    r"ve sinh vuon|mat do|khoang cach|che phu|"
    r"thuoc|hoa chat|hoat chat|lieu|nong do|pha|cach ly|"
    r"thu hoach|tai canh|cay giong|dat|do am|nhiet do|ph"
    r")\b"
)
_DIRECTIVE_PATTERN = re.compile(
    r"\b(?:nen|can|hay|tranh|uu tien|khong nen)\s+[a-z0-9]"
)
_RESPONSE_FRAMING_PATTERN = re.compile(
    r"^(?:de\b.*(?:"
    r"\bminh\s+(?:(?:xin|da)\s+)?"
    r"(?:chia se|trinh bay|tom tat|huong dan|tong hop|chuan bi)\b.*"
    r"|\b(?:yeu to|nguyen tac|noi dung|cach|bien phap)\b.*"
    r"\b(?:nhu sau|sau day|duoi day|sau)"
    r")|(?:duoi day|sau day)\b.*)\s*:$"
)
_EXEMPT_PATTERNS = (
    "chua du thong tin",
    "chua du bang chung",
    "chua the ket luan",
    "khong the ket luan",
    "minh chua chac chan",
    "can them anh",
    "gui them anh",
    "bo sung thong tin",
    "cho minh biet them",
    "hoi can bo khuyen nong",
    "tham khao can bo khuyen nong",
    "doc ky nhan",
    "lam theo nhan",
)
_DIRECT_OBSERVATION_PATTERNS = (
    "quan sat truc tiep",
    "trong anh",
    "anh cho thay",
    "co the thay trong anh",
    "nhin thay",
)
_INTERPRETIVE_PATTERNS = (
    "co the la",
    "nguyen nhan",
    "do ",
    "benh",
    "gia thuyet",
    "chan doan",
)


def referenced_evidence_indexes(answer: str | None) -> list[int]:
    """Return unique evidence indexes in first-claim order."""
    return list(dict.fromkeys(
        int(value) for value in _CITATION_MARKER_PATTERN.findall(answer or "")
    ))


def _move_markers_before_terminators(line: str) -> str:
    """Keep a trailing evidence marker attached to its preceding sentence."""
    return re.sub(
        r"([.!?])\s*((?:\[E\d+\]\s*)+)",
        r"\2\1 ",
        line,
        flags=re.IGNORECASE,
    ).strip()


def _split_sentences(line: str) -> list[str]:
    """Split prose without treating lowercase text after abbreviations as new."""
    sentence_start = 0
    sentences: list[str] = []
    for boundary in re.finditer(r"(?<=[.!?])\s+", line):
        remainder = line[boundary.end():].lstrip(" *_`\"'([{ ")
        if not remainder or not (
            remainder[0].isupper() or remainder[0].isdigit()
        ):
            continue
        sentences.append(line[sentence_start:boundary.start()])
        sentence_start = boundary.end()
    sentences.append(line[sentence_start:])
    return sentences


def _is_short_heading(line: str) -> bool:
    heading_text = re.sub(r"[*_`]+", "", line).strip()
    return heading_text.endswith(":") and len(heading_text.split()) <= 10


def _claim_units(answer: str | None) -> list[str]:
    """Split prose and bullets while keeping a trailing marker with its claim."""
    units: list[str] = []
    for raw_line in (answer or "").splitlines():
        line = _MARKDOWN_PREFIX_PATTERN.sub("", raw_line).strip()
        if not line:
            continue
        line = _move_markers_before_terminators(line)
        heading_text = re.sub(r"[*_`]+", "", line).strip()
        if _is_short_heading(heading_text):
            continue
        for sentence in _split_sentences(line):
            sentence = sentence.strip()
            if not sentence or _MARKER_ONLY_PATTERN.fullmatch(sentence):
                continue
            units.append(sentence)
    return units


def _is_direct_observation(normalized_claim: str) -> bool:
    return any(
        phrase in normalized_claim for phrase in _DIRECT_OBSERVATION_PATTERNS
    ) and not any(
        phrase in normalized_claim for phrase in _INTERPRETIVE_PATTERNS
    )


def claim_requires_citation(claim: str) -> bool:
    """Return whether a sentence makes a source-dependent technical claim."""
    stripped = claim.strip()
    if not stripped or stripped.endswith("?"):
        return False
    normalized = " ".join(normalize_vietnamese(stripped).split())
    # A long lead-in may mention the topic (for example ``dat`` or ``benh``)
    # without asserting any agricultural fact. Treat only the narrowly shaped
    # first-person list introduction as framing; actual directives or factual
    # sentences that follow remain subject to citation checks.
    if _RESPONSE_FRAMING_PATTERN.fullmatch(normalized):
        return False
    if any(pattern in normalized for pattern in _EXEMPT_PATTERNS):
        return False
    if _is_direct_observation(normalized):
        return False
    return bool(
        _TECHNICAL_PATTERN.search(normalized)
        or _DIRECTIVE_PATTERN.search(normalized)
    )


def uncited_technical_claims(answer: str | None) -> list[str]:
    """Return source-dependent claim units that lack a local ``[E#]`` marker."""
    return [
        claim
        for claim in _claim_units(answer)
        if claim_requires_citation(claim)
        and not _CITATION_MARKER_PATTERN.search(claim)
    ]


def _is_judgeable_claim(claim: str) -> bool:
    """Judge every detected technical claim and every explicitly cited fact."""
    return bool(
        claim_requires_citation(claim)
        or _CITATION_MARKER_PATTERN.search(claim)
    )


def technical_claim_units(answer: str | None) -> list[str]:
    """Return stable, one-based units for structured entailment judging."""
    return [
        claim for claim in _claim_units(answer) if _is_judgeable_claim(claim)
    ]


def prune_uncited_technical_claims(
    answer: str | None,
) -> tuple[str, list[str]]:
    """Remove only residual uncited technical sentences after model repair.

    The result still goes through reflection and the post-guardrail. This is a
    bounded fail-soft step: supported sentences remain useful to the user,
    while unsupported advice is never released merely to keep prose fluent.
    """
    kept_lines: list[str] = []
    removed: list[str] = []
    for raw_line in (answer or "").splitlines():
        if not raw_line.strip():
            kept_lines.append("")
            continue
        line = _move_markers_before_terminators(raw_line.strip())
        kept_sentences: list[str] = []
        for sentence in _split_sentences(line):
            sentence = sentence.strip()
            claim = _MARKDOWN_PREFIX_PATTERN.sub("", sentence).strip()
            if (
                claim
                and not _is_short_heading(claim)
                and _is_judgeable_claim(claim)
                and not _CITATION_MARKER_PATTERN.search(claim)
            ):
                removed.append(claim)
                continue
            if sentence:
                kept_sentences.append(sentence)
        if kept_sentences:
            kept_lines.append(" ".join(kept_sentences))
    pruned = "\n".join(kept_lines).strip()
    pruned = re.sub(r"\n{3,}", "\n\n", pruned)
    return pruned, removed


def _exact_claim_key(value: str) -> str:
    """Normalize presentation details without allowing fuzzy claim matches."""
    without_prefix = _MARKDOWN_PREFIX_PATTERN.sub("", value).strip()
    without_markers = _CITATION_MARKER_PATTERN.sub("", without_prefix)
    normalized = " ".join(normalize_vietnamese(without_markers).split())
    return normalized.strip(" \t\r\n.!?;:")


def prune_exact_rejected_claims(
    answer: str | None,
    rejected_claims: list[str] | None,
) -> tuple[str, list[str]]:
    """Remove only sentences copied exactly by the entailment judge.

    Citation markers and Markdown list prefixes are presentation metadata, so
    they are ignored for equality. Wording must otherwise match exactly; a
    paraphrase or substring never authorizes deletion. The caller must run the
    resulting answer through reflection and the post-guardrail again.
    """
    rejected_keys = {
        key
        for claim in (rejected_claims or [])
        if (key := _exact_claim_key(str(claim)))
    }
    if not rejected_keys:
        return (answer or "").strip(), []

    kept_lines: list[str] = []
    removed: list[str] = []
    for raw_line in (answer or "").splitlines():
        if not raw_line.strip():
            kept_lines.append("")
            continue
        line = _move_markers_before_terminators(raw_line.strip())
        kept_sentences: list[str] = []
        for sentence in _split_sentences(line):
            sentence = sentence.strip()
            claim = _MARKDOWN_PREFIX_PATTERN.sub("", sentence).strip()
            if claim and _exact_claim_key(claim) in rejected_keys:
                removed.append(claim)
                continue
            if sentence:
                kept_sentences.append(sentence)
        if kept_sentences:
            kept_lines.append(" ".join(kept_sentences))
    pruned = "\n".join(kept_lines).strip()
    pruned = re.sub(r"\n{3,}", "\n\n", pruned)
    return pruned, removed


def prune_rejected_claim_ids(
    answer: str | None,
    rejected_claim_ids: list[int] | None,
) -> tuple[str, list[str]]:
    """Remove only numbered technical claims previously shown to the judge."""
    requested_ids = list(dict.fromkeys(
        claim_id
        for claim_id in (rejected_claim_ids or [])
        if isinstance(claim_id, int) and not isinstance(claim_id, bool)
        and claim_id > 0
    ))
    if not requested_ids:
        return (answer or "").strip(), []
    claims = technical_claim_units(answer)
    if any(claim_id > len(claims) for claim_id in requested_ids):
        return (answer or "").strip(), []
    exact_claims = [claims[claim_id - 1] for claim_id in requested_ids]
    return prune_exact_rejected_claims(answer, exact_claims)
