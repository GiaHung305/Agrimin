"""Fetch, validate and idempotently ingest an audited crop-data batch."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from pypdf import PdfReader
from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.db import AsyncSessionLocal
from app.persistence.models import Document
from app.retrieval.source_authority import SourceType, normalize_source_type
from app.services.farm_monitoring import POLICIES
from app.services.ingest_service import (
    ingest_document,
    update_document_published_date,
)


logger = logging.getLogger(__name__)
DEFAULT_MANIFEST = Path(__file__).with_name("crop_data_expansion_batch_1_v1.json")
DEFAULT_REPORT = Path(__file__).with_name("crop_data_expansion_batch_1_report.json")
MAX_SOURCE_BYTES = 15 * 1024 * 1024
SOURCE_FETCH_ATTEMPTS = 3


class ElementTextExtractor(HTMLParser):
    """Extract visible text from one HTML element selected by id or class."""

    block_tags = {"br", "div", "h1", "h2", "h3", "h4", "li", "p", "tr"}
    void_tags = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(
        self, element_id: str | None = None, element_class: str | None = None
    ):
        super().__init__(convert_charrefs=True)
        self.element_id = element_id
        self.element_class = element_class
        self.depth = 0
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if self.depth == 0:
            classes = str(attributes.get("class") or "").split()
            matches_id = bool(
                self.element_id and attributes.get("id") == self.element_id
            )
            matches_class = bool(
                self.element_class and self.element_class in classes
            )
            if matches_id or matches_class:
                self.depth = 1
                return
        if not self.depth:
            return
        if tag in self.void_tags:
            if tag in self.block_tags:
                self.parts.append("\n")
            return
        self.depth += 1
        if tag in {"script", "style"}:
            self.ignored_depth += 1
        if tag in self.block_tags:
            self.parts.append("\n")

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if self.depth and tag in self.block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if not self.depth:
            return
        if tag in {"script", "style"} and self.ignored_depth:
            self.ignored_depth -= 1
        if tag in self.block_tags:
            self.parts.append("\n")
        self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.depth and not self.ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        return _clean_text("".join(self.parts))


class DnnVoiceTextExtractor(HTMLParser):
    """Extract the summary and article content exposed to DNN text-to-speech."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.summary: str | None = None
        self.content: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "input":
            return
        attributes = dict(attrs)
        element_id = str(attributes.get("id") or "")
        value = attributes.get("value")
        if value is None:
            return
        if element_id.endswith("HidSummaryVoice"):
            self.summary = value
        elif element_id.endswith("HidContentVoice"):
            self.content = value

    def text(self) -> str:
        if not self.content:
            raise ValueError("crop_batch_dnn_voice_content_missing")
        return _clean_text("\n".join(part for part in (self.summary, self.content) if part))


class BodyTextExtractor(HTMLParser):
    """Extract visible HTML text for sources bounded by audited markers."""

    block_tags = {"br", "div", "h1", "h2", "h3", "h4", "li", "p", "tr"}
    ignored_tags = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.ignored_tags:
            self.ignored_depth += 1
        if not self.ignored_depth and tag in self.block_tags:
            self.parts.append("\n")

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if not self.ignored_depth and tag in self.block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.ignored_tags and self.ignored_depth:
            self.ignored_depth -= 1
            return
        if not self.ignored_depth and tag in self.block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        return _clean_text("".join(self.parts))


def _clean_text(value: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def _normalized(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(char) != "Mn"
    ).replace("đ", "d")


def parse_database_datetime(value: str) -> datetime:
    """Parse an ISO timestamp for the repository's UTC-naive DateTime column."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    allowed_domains = set(payload.get("allowed_domains", []))
    documents = payload.get("documents")
    if not payload.get("version") or not allowed_domains:
        raise ValueError("crop_batch_version_and_domains_required")
    if not isinstance(documents, list) or not documents:
        raise ValueError("crop_batch_documents_required")
    titles = [str(item.get("title", "")).strip() for item in documents]
    if len(titles) != len(set(titles)):
        raise ValueError("crop_batch_duplicate_title")

    for item in documents:
        for field in ("title", "source", "source_type", "format", "author"):
            if not str(item.get(field, "")).strip():
                raise ValueError(f"crop_batch_{field}_required")
        parsed = urlparse(item["source"])
        if parsed.scheme != "https" or parsed.hostname not in allowed_domains:
            raise ValueError(f"crop_batch_source_not_allowed:{item['source']}")
        if normalize_source_type(item["source_type"]) is SourceType.UNKNOWN:
            raise ValueError("crop_batch_authoritative_source_type_required")
        if item.get("published_date"):
            try:
                parse_database_datetime(str(item["published_date"]))
            except ValueError as exc:
                raise ValueError("crop_batch_published_date_invalid") from exc
        unknown_crops = set(item.get("crop_keys", [])) - set(POLICIES)
        if unknown_crops:
            raise ValueError(
                "crop_batch_unknown_crop_keys:" + ",".join(sorted(unknown_crops))
            )
        if not item.get("required_terms") or int(item.get("min_chars", 0)) < 500:
            raise ValueError("crop_batch_content_validation_required")
        if item["format"] == "pdf":
            start, end = item.get("page_start"), item.get("page_end")
            if not isinstance(start, int) or not isinstance(end, int) or start > end:
                raise ValueError("crop_batch_pdf_page_range_invalid")
        elif item["format"] == "html":
            selectors = [item.get("element_id"), item.get("element_class")]
            if sum(bool(selector) for selector in selectors) != 1:
                raise ValueError("crop_batch_html_single_selector_required")
        elif item["format"] == "dnn_voice":
            pass
        elif item["format"] == "html_markers":
            if not item.get("start_marker") or not item.get("end_marker"):
                raise ValueError("crop_batch_html_markers_required")
            exclusions = item.get("exclude_marker_ranges", [])
            if not isinstance(exclusions, list) or any(
                not isinstance(exclusion, dict)
                or not exclusion.get("start_marker")
                or not exclusion.get("end_marker")
                for exclusion in exclusions
            ):
                raise ValueError("crop_batch_exclude_marker_ranges_invalid")
        elif item["format"] == "text_markers":
            if not item.get("start_marker") or not item.get("end_marker"):
                raise ValueError("crop_batch_text_markers_required")
            exclusions = item.get("exclude_marker_ranges", [])
            if not isinstance(exclusions, list) or any(
                not isinstance(exclusion, dict)
                or not exclusion.get("start_marker")
                or not exclusion.get("end_marker")
                for exclusion in exclusions
            ):
                raise ValueError("crop_batch_exclude_marker_ranges_invalid")
        else:
            raise ValueError(f"crop_batch_format_unsupported:{item['format']}")
        forbidden_terms = item.get("forbidden_terms", [])
        if not isinstance(forbidden_terms, list) or any(
            not isinstance(term, str) or not term.strip()
            for term in forbidden_terms
        ):
            raise ValueError("crop_batch_forbidden_terms_invalid")
    return payload


def extract_pdf_pages(file_bytes: bytes, start_page: int, end_page: int) -> str:
    if not file_bytes.startswith(b"%PDF-"):
        raise ValueError("crop_batch_invalid_pdf_signature")
    reader = PdfReader(BytesIO(file_bytes))
    if start_page < 1 or end_page > len(reader.pages):
        raise ValueError("crop_batch_pdf_page_range_out_of_bounds")
    text = "\n".join(
        reader.pages[index].extract_text() or ""
        for index in range(start_page - 1, end_page)
    )
    return _clean_text(text)


def slice_markers(
    content: str, start_marker: str | None, end_marker: str | None
) -> str:
    start = 0
    if start_marker:
        start = content.find(start_marker)
        if start < 0:
            raise ValueError(f"crop_batch_start_marker_missing:{start_marker}")
    end = len(content)
    if end_marker:
        end = content.find(end_marker, start + len(start_marker or ""))
        if end < 0:
            raise ValueError(f"crop_batch_end_marker_missing:{end_marker}")
    return content[start:end].strip()


def exclude_marker_ranges(
    content: str, ranges: list[dict[str, str]] | None
) -> str:
    """Remove explicitly audited spans while retaining their end markers.

    This is used for source sections where safe cultural/IPM guidance surrounds
    a legacy chemical recommendation. Missing or reversed markers fail closed.
    """
    result = content
    for marker_range in ranges or []:
        start_marker = marker_range["start_marker"]
        end_marker = marker_range["end_marker"]
        start = result.find(start_marker)
        if start < 0:
            raise ValueError(f"crop_batch_exclude_start_marker_missing:{start_marker}")
        end = result.find(end_marker, start + len(start_marker))
        if end < 0:
            raise ValueError(f"crop_batch_exclude_end_marker_missing:{end_marker}")
        result = f"{result[:start]}{result[end:]}"
    return _clean_text(result)


def extract_html_element(
    file_bytes: bytes,
    element_id: str | None = None,
    element_class: str | None = None,
) -> str:
    parser = ElementTextExtractor(element_id, element_class)
    parser.feed(file_bytes.decode("utf-8", errors="replace"))
    text = parser.text()
    if not text:
        selector = element_id or element_class
        raise ValueError(f"crop_batch_html_element_missing:{selector}")
    return text


def extract_dnn_voice(file_bytes: bytes) -> str:
    parser = DnnVoiceTextExtractor()
    parser.feed(file_bytes.decode("utf-8", errors="replace"))
    return parser.text()


def extract_html_body(file_bytes: bytes) -> str:
    parser = BodyTextExtractor()
    parser.feed(file_bytes.decode("utf-8", errors="replace"))
    text = parser.text()
    if not text:
        raise ValueError("crop_batch_html_body_missing")
    return text


def extract_plain_text(file_bytes: bytes) -> str:
    """Decode an authoritative text rendition before audited marker slicing."""
    text = _clean_text(file_bytes.decode("utf-8", errors="replace"))
    if not text:
        raise ValueError("crop_batch_plain_text_missing")
    return text


def validate_content(entry: dict[str, Any], content: str) -> None:
    if len(content) < int(entry["min_chars"]):
        raise ValueError(f"crop_batch_content_too_short:{entry['title']}")
    normalized = _normalized(content)
    missing = [
        term for term in entry["required_terms"] if _normalized(term) not in normalized
    ]
    if missing:
        raise ValueError(
            f"crop_batch_required_terms_missing:{entry['title']}:" + ",".join(missing)
        )
    forbidden = [
        term
        for term in entry.get("forbidden_terms", [])
        if _normalized(term) in normalized
    ]
    if forbidden:
        raise ValueError(
            f"crop_batch_forbidden_terms_present:{entry['title']}:"
            + ",".join(forbidden)
        )


async def fetch_sources(
    manifest: dict[str, Any],
) -> dict[str, bytes]:
    urls = sorted({entry["source"] for entry in manifest["documents"]})
    payloads: dict[str, bytes] = {}
    timeout = httpx.Timeout(60.0, connect=15.0)
    headers = {"User-Agent": "AgriMind corpus curator/1.0"}
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=True, headers=headers
    ) as client:
        for url in urls:
            response: httpx.Response | None = None
            for attempt in range(1, SOURCE_FETCH_ATTEMPTS + 1):
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    break
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code < 500 or attempt == SOURCE_FETCH_ATTEMPTS:
                        raise
                    logger.warning(
                        "Crop source returned retryable HTTP status url=%s status=%s attempt=%s/%s",
                        url,
                        exc.response.status_code,
                        attempt,
                        SOURCE_FETCH_ATTEMPTS,
                    )
                except httpx.TransportError:
                    if attempt == SOURCE_FETCH_ATTEMPTS:
                        raise
                    logger.warning(
                        "Crop source transport failure url=%s attempt=%s/%s",
                        url,
                        attempt,
                        SOURCE_FETCH_ATTEMPTS,
                    )
                await asyncio.sleep(2 ** (attempt - 1))
            if response is None:
                raise RuntimeError(f"crop_batch_source_fetch_failed:{url}")
            content = response.content
            if not content or len(content) > MAX_SOURCE_BYTES:
                raise ValueError(f"crop_batch_source_size_invalid:{url}")
            payloads[url] = content
    return payloads


def prepare_documents(
    manifest: dict[str, Any], payloads: dict[str, bytes]
) -> list[dict[str, Any]]:
    prepared = []
    for entry in manifest["documents"]:
        source_bytes = payloads[entry["source"]]
        if entry["format"] == "pdf":
            content = extract_pdf_pages(
                source_bytes, entry["page_start"], entry["page_end"]
            )
        elif entry["format"] == "html":
            content = extract_html_element(
                source_bytes,
                element_id=entry.get("element_id"),
                element_class=entry.get("element_class"),
            )
        elif entry["format"] == "html_markers":
            content = extract_html_body(source_bytes)
        elif entry["format"] == "text_markers":
            content = extract_plain_text(source_bytes)
        else:
            content = extract_dnn_voice(source_bytes)
        content = slice_markers(
            content, entry.get("start_marker"), entry.get("end_marker")
        )
        content = exclude_marker_ranges(
            content, entry.get("exclude_marker_ranges")
        )
        if entry.get("content_prefix"):
            content = _clean_text(f"{entry['content_prefix']}\n{content}")
        validate_content(entry, content)
        prepared.append(
            {
                **entry,
                "content": content,
                "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            }
        )
    return prepared


async def ingest_batch(
    manifest_path: Path = DEFAULT_MANIFEST,
    report_path: Path = DEFAULT_REPORT,
    *,
    apply: bool = False,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    prepared = prepare_documents(manifest, await fetch_sources(manifest))
    summary: dict[str, Any] = {
        "version": manifest["version"],
        "documents": len(prepared),
        "sources": len({item["source"] for item in prepared}),
        "ready": 0,
        "already_active": 0,
        "replace_ready": 0,
        "ingested": 0,
        "replaced": 0,
        "items": [],
    }

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document).where(
                Document.title.in_([entry["title"] for entry in prepared]),
                Document.is_active.is_(True),
            )
        )
        existing = {document.title: document for document in result.scalars().all()}
        for entry in prepared:
            document = existing.get(entry["title"])
            expected_version = entry.get("version", manifest["version"])
            can_replace = bool(
                entry.get("replace_active")
                and document
                and document.source == entry["source"]
                and document.source_type == entry["source_type"]
                and document.version != expected_version
            )
            if document and not can_replace and (
                document.source != entry["source"]
                or document.version != expected_version
                or document.source_type != entry["source_type"]
            ):
                raise ValueError(f"crop_batch_active_document_drift:{entry['title']}")

        for entry in prepared:
            current = existing.get(entry["title"])
            expected_version = entry.get("version", manifest["version"])
            published_date = (
                parse_database_datetime(entry["published_date"])
                if entry.get("published_date")
                else None
            )
            replace = bool(
                current
                and entry.get("replace_active")
                and current.version != expected_version
            )
            status = "replace_ready" if replace else ("already_active" if current else "ready")
            if replace:
                summary["replace_ready"] += 1
            elif current:
                summary["already_active"] += 1
            else:
                summary["ready"] += 1
            item = {
                "title": entry["title"],
                "source": entry["source"],
                "crop_keys": entry["crop_keys"],
                "characters": len(entry["content"]),
                "content_sha256": entry["content_sha256"],
                "source_sha256": entry["source_sha256"],
                "status": status,
            }
            if apply and (not current or replace):
                document = await ingest_document(
                    db=db,
                    title=entry["title"],
                    content=entry["content"],
                    source=entry["source"],
                    source_type=entry["source_type"],
                    author=entry["author"],
                    version=expected_version,
                    published_date=published_date,
                )
                item["status"] = "replaced" if replace else "ingested"
                item["document_id"] = str(document.id)
                if replace:
                    summary["replaced"] += 1
                else:
                    summary["ingested"] += 1
            elif current:
                item["document_id"] = str(current.id)
            if apply and published_date:
                persisted = document if (not current or replace) else current
                if persisted.published_date != published_date:
                    await update_document_published_date(
                        db, persisted, published_date
                    )
            summary["items"].append(item)

    report_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    summary = asyncio.run(
        ingest_batch(args.manifest, args.report, apply=args.apply)
    )
    logger.info(
        "Crop data batch summary: %s",
        {key: value for key, value in summary.items() if key != "items"},
    )


if __name__ == "__main__":
    main()
