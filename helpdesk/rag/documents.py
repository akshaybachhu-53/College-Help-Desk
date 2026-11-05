"""Reading the document collection and cutting it into retrievable chunks.

Each chunk keeps enough metadata to produce a citation a student can check:
document title + page (PDF) or section heading (Markdown), plus whether the document
is current or superseded (old regulations are kept on purpose: students from older
batches still ask about them, and it lets us test whether the agent prefers the
current rule).
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from helpdesk import config


@dataclass
class DocInfo:
    doc_id: str
    filename: str
    title: str
    doc_type: str
    period: str
    status: str  # current | superseded
    url: str = ""

    @property
    def path(self) -> Path:
        return config.RAW_DIR / self.filename


@dataclass
class Chunk:
    chunk_id: str
    text: str
    meta: dict = field(default_factory=dict)


def load_manifest(only_text_docs: bool = True) -> list[DocInfo]:
    docs = []
    with config.MANIFEST.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if only_text_docs and r["doc_type"].startswith("table"):
                continue  # CSV tables are served by tools, not by the vector store
            docs.append(DocInfo(r["doc_id"], r["filename"], r["title"], r["doc_type"],
                                r["period"], r["status"], r.get("url", "")))
    return docs


def doc_index() -> dict[str, DocInfo]:
    return {d.doc_id: d for d in load_manifest(only_text_docs=False)}


# ---------------------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------------------
_HINDI_GARBLE = re.compile(r"^[^A-Za-z0-9]*$")


def _clean_pdf_text(text: str) -> str:
    lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        # header/footer noise that repeats on every page of institute PDFs
        if re.fullmatch(r"(Website: )?(https?://)?www\.iitj\.ac\.in.*", s, re.I) or re.fullmatch(r"\d+( \| Page)?", s):
            continue
        if s in ("Indian Institute of Technology Jodhpur", "Office of Academic Affairs"):
            continue
        # the Devanagari letterhead is extracted as mojibake (e.g. "Hkkjrh; çkS|ksfxdh")
        if re.search(r"[çÌ|]{1}.*[;]|Hkkjrh|dk;k", s):
            continue
        lines.append(s)
    return "\n".join(lines)


def read_pdf(path: Path) -> list[tuple[str, str]]:
    """[(locator, text)] with locator 'p. N'."""
    out = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            txt = _clean_pdf_text(page.extract_text() or "")
            if len(txt) > 40:
                out.append((f"p. {i}", txt))
    return out


def read_markdown(path: Path) -> list[tuple[str, str]]:
    """Split on '## ' headings; locator is the section heading."""
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^##\s+", text)
    out = []
    head = parts[0].strip()
    if head:
        out.append(("introduction", head))
    for part in parts[1:]:
        title, _, body = part.partition("\n")
        out.append((f"section '{title.strip()}'", f"{title.strip()}\n{body.strip()}"))
    return out


def read_document(doc: DocInfo) -> list[tuple[str, str]]:
    if doc.path.suffix.lower() == ".pdf":
        return read_pdf(doc.path)
    return read_markdown(doc.path)


# ---------------------------------------------------------------------------------------
# chunking
# ---------------------------------------------------------------------------------------
def _split_long(text: str, size: int, overlap: int) -> list[str]:
    """Greedy split on line boundaries; tables stay row-aligned instead of being cut mid-row."""
    lines = text.splitlines()
    chunks, cur = [], ""
    for ln in lines:
        if len(cur) + len(ln) + 1 > size and cur:
            chunks.append(cur.strip())
            tail = cur[-overlap:]
            cur = tail[tail.find("\n") + 1:] if "\n" in tail else tail
        cur += ln + "\n"
    if cur.strip():
        chunks.append(cur.strip())
    return chunks


def chunk_document(doc: DocInfo) -> list[Chunk]:
    chunks: list[Chunk] = []
    for locator, text in read_document(doc):
        for j, piece in enumerate(_split_long(text, config.CHUNK_CHARS, config.CHUNK_OVERLAP)):
            # A short header inside the embedded text helps the 8B model and the
            # embedder: "Academic Calendar AY 2026-27 (p. 2)" carries meaning by itself.
            header = f"[{doc.title} | {locator}]"
            chunks.append(Chunk(
                chunk_id=f"{doc.doc_id}-{re.sub(r'[^a-z0-9]+', '', locator.lower())[:30]}-{j}",
                text=f"{header}\n{piece}",
                meta={"doc_id": doc.doc_id, "title": doc.title, "locator": locator,
                      "status": doc.status, "period": doc.period, "doc_type": doc.doc_type,
                      "filename": doc.filename},
            ))
    return chunks
