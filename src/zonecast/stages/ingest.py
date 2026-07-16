"""Stage 1 — ingestion (PRD FR-1, §12 error matrix).

Normalizes exactly one source (topic string | local PDF | URL) into the episode's ``source/``
dir: always ``source/meta.json`` (type, ref, title, plus any detectable bibliographic fields),
and for PDF/URL sources the extracted full text as ``source/paper.md``. No LLM call here.
"""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

import fitz  # pymupdf

from ..pipeline import Stage, mark_complete

if TYPE_CHECKING:
    from . import StageContext

# Below this many extracted characters we treat a PDF as empty/garbled (scanned image, DRM,
# broken encoding) and abort with an actionable message instead of feeding noise downstream.
_MIN_PDF_CHARS = 200

_ARXIV_ABS = re.compile(r"arxiv\.org/abs/(?P<id>[\w.\-/]+?)(?:v\d+)?/?$", re.IGNORECASE)
_USER_AGENT = "zonecast/0.1 (+https://github.com/; personal explainer-podcast generator)"


def run(ctx: "StageContext") -> None:
    args = ctx.args
    provided = [x for x in (args.topic, args.pdf, args.url) if x]
    if len(provided) != 1:
        raise ValueError(
            "ingest requires exactly one source: a topic string, --pdf, or --url "
            f"(got {len(provided)})."
        )

    if args.pdf is not None:
        _ingest_pdf(ctx, args.pdf)
    elif args.url is not None:
        _ingest_url(ctx, args.url)
    else:
        assert args.topic is not None
        _ingest_topic(ctx, args.topic)

    mark_complete(ctx.episode_dir, Stage.ingest)


# --- topic --------------------------------------------------------------------------------


def _ingest_topic(ctx: "StageContext", topic: str) -> None:
    ctx.write_json("source/meta.json", {"type": "topic", "ref": topic, "title": topic})


# --- pdf ----------------------------------------------------------------------------------


def _ingest_pdf(ctx: "StageContext", pdf: Path) -> None:
    if not pdf.exists():
        raise FileNotFoundError(f"PDF not found: {pdf}")
    with fitz.open(pdf) as doc:
        text, meta = _extract_pdf(doc)
    _persist_document(ctx, text, meta, source_type="pdf", ref=str(pdf), fallback_title=pdf.stem)


def _ingest_url(ctx: "StageContext", url: str) -> None:
    pdf_url = _resolve_pdf_url(url)
    data = _fetch(pdf_url)
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            text, meta = _extract_pdf(doc)
    except Exception as exc:  # not a PDF, or unreadable
        raise ValueError(
            f"Could not read a PDF from {pdf_url!r}. If this is an arXiv abstract page, pass the "
            f"abstract URL directly (arxiv.org/abs/ID) so the PDF can be derived. Original: {exc}"
        ) from exc
    _persist_document(ctx, text, meta, source_type="url", ref=url, fallback_title=_url_title(url))


def _persist_document(
    ctx: "StageContext",
    text: str,
    meta: dict[str, Any],
    *,
    source_type: str,
    ref: str,
    fallback_title: str,
) -> None:
    if len(text.strip()) < _MIN_PDF_CHARS:
        # §12: empty/garbled extraction -> abort with a route forward, not silent noise.
        raise ValueError(
            "PDF text extraction was empty or garbled (likely a scanned or image-only PDF). "
            "Try the arXiv abstract URL instead: zonecast create --url https://arxiv.org/abs/<id>"
        )
    ctx.write_text("source/paper.md", text)
    record: dict[str, Any] = {
        "type": source_type,
        "ref": ref,
        "title": meta.get("title") or fallback_title,
    }
    for key in ("authors", "year"):
        if meta.get(key):
            record[key] = meta[key]
    ctx.write_json("source/meta.json", record)


def _extract_pdf(doc: "fitz.Document") -> tuple[str, dict[str, Any]]:
    """Extract full text (section structure preserved via the PDF outline where present) and
    any detectable title/authors/year from the document metadata."""
    parts: list[str] = []
    toc = doc.get_toc()  # [[level, title, page], ...]; empty when no outline exists
    heads_by_page: dict[int, list[str]] = {}
    for _level, title, page in toc:
        heads_by_page.setdefault(page - 1, []).append(title)

    for i, page in enumerate(doc):
        for head in heads_by_page.get(i, []):
            parts.append(f"\n## {head}\n")
        parts.append(page.get_text("text"))
    text = "\n".join(parts).strip()

    md = doc.metadata or {}
    meta: dict[str, Any] = {}
    if md.get("title"):
        meta["title"] = md["title"].strip()
    if md.get("author"):
        meta["authors"] = md["author"].strip()
    year = _detect_year(md)
    if year:
        meta["year"] = year
    return text, meta


def _detect_year(md: dict[str, Any]) -> str | None:
    for field in ("creationDate", "modDate"):
        m = re.search(r"(19|20)\d{2}", str(md.get(field, "")))
        if m:
            return m.group(0)
    return None


# --- url helpers --------------------------------------------------------------------------


def _resolve_pdf_url(url: str) -> str:
    """arXiv abstract URL -> its PDF URL; anything else is fetched as-is."""
    m = _ARXIV_ABS.search(url)
    if m:
        return f"https://arxiv.org/pdf/{m.group('id')}.pdf"
    return url


def _url_title(url: str) -> str:
    m = _ARXIV_ABS.search(url)
    if m:
        return f"arXiv {m.group('id')}"
    return _url_slug_source(url)


def _url_slug_source(url: str) -> str:
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"\.pdf$", "", tail, flags=re.IGNORECASE) or url


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (trusted user-supplied URL)
        return resp.read()
