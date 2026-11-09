"""Load the knowledge base: read each document, parse its metadata, split it into chunks.

No embeddings here. This module only turns files into Doc and Chunk objects,
so it can be tested without an API key.
"""
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from app import config

# Front matter sits between two '---' lines. PDFs put the words "DOCUMENT CONTROL"
# before the first one, so the pattern allows an optional prefix.
FRONT_MATTER = re.compile(r"^\s*(?:DOCUMENT CONTROL\s*)?---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Every PDF page ends with a footer line. On KB-012 the text extractor glues the
# footer to the next line, so we remove it with a pattern instead of by line.
PDF_FOOTER = re.compile(r"Nakhla Systems \(fictional\) · (?:KB|SP)-\d+ v[\d.]+ · .*? · page \d+ of \d+")

REQUIRED_FIELDS = ("id", "title", "status", "authoritative")


@dataclass
class Doc:
    id: str
    title: str
    version: str
    last_updated: str
    status: str            # current | deprecated | draft
    authoritative: bool
    owner: str
    supersedes: str | None
    applies_to: list[str]
    tags: list[str]
    error_codes: list[str]
    body: str
    path: Path


@dataclass
class Chunk:
    doc_id: str
    section: str
    text: str


def read_pdf_text(path: Path) -> str:
    """Return the text of every page of a PDF, joined with newlines."""
    import pymupdf  # imported here so Markdown-only use does not need it

    with pymupdf.open(path) as pdf:
        return "\n".join(page.get_text() for page in pdf)


def parse_document(raw: str, path: Path) -> Doc:
    """Split raw text into metadata (front matter) and body."""
    match = FRONT_MATTER.match(raw)
    if not match:
        raise ValueError(f"{path.name}: no front matter found")
    meta = yaml.safe_load(match.group(1))
    missing = [f for f in REQUIRED_FIELDS if f not in meta]
    if missing:
        raise ValueError(f"{path.name}: front matter is missing {missing}")

    body = raw[match.end():]
    if path.suffix == ".pdf":
        body = PDF_FOOTER.sub("", body)

    return Doc(
        id=meta["id"],
        title=meta["title"],
        version=str(meta.get("version", "")),
        last_updated=str(meta.get("last_updated", "")),  # YAML gives a date object
        status=meta["status"],
        authoritative=bool(meta["authoritative"]),
        owner=meta.get("owner", ""),
        supersedes=meta.get("supersedes"),
        applies_to=meta.get("applies_to") or [],
        tags=meta.get("tags") or [],
        error_codes=meta.get("error_codes") or [],
        body=body.strip(),
        path=path,
    )


def load_docs(kb_dir: Path = config.KB_DIR) -> dict[str, Doc]:
    """Read every .md and .pdf file in the folder. Returns {doc_id: Doc}."""
    docs: dict[str, Doc] = {}
    for path in sorted(kb_dir.iterdir()):
        if path.suffix not in (".md", ".pdf"):
            continue
        raw = read_pdf_text(path) if path.suffix == ".pdf" else path.read_text(encoding="utf-8")
        doc = parse_document(raw, path)
        if doc.id in docs:
            raise ValueError(f"duplicate document id {doc.id}")
        docs[doc.id] = doc
    return docs


def searchable_docs(docs: dict[str, Doc]) -> list[Doc]:
    """Only these documents may become chunks. Draft and deprecated ones stay out."""
    return [d for d in docs.values() if d.status in config.SEARCHABLE_STATUSES]


def _split_long(text: str, limit: int) -> list[str]:
    """Split text at blank lines so that no piece is much longer than limit."""
    pieces, current = [], ""
    for para in text.split("\n\n"):
        if current and len(current) + len(para) > limit:
            pieces.append(current.strip())
            current = ""
        current += para + "\n\n"
    if current.strip():
        pieces.append(current.strip())
    return pieces


def _markdown_sections(body: str) -> list[tuple[str, str]]:
    """Cut a Markdown body at '## ' headings. Text before the first one is the overview."""
    parts = re.split(r"^## +(.+)$", body, flags=re.MULTILINE)
    # parts = [intro, heading1, text1, heading2, text2, ...]
    intro = re.sub(r"^# .*$", "", parts[0], flags=re.MULTILINE).strip()
    sections = [("Overview", intro)] if intro else []
    sections += [(parts[i].strip(), parts[i + 1].strip()) for i in range(1, len(parts), 2)]
    return sections


def _pdf_sections(body: str) -> list[tuple[str, str]]:
    """PDFs have no heading markers, so we keep the whole text as one section."""
    return [("Full text", body)]


def chunk_doc(doc: Doc) -> list[Chunk]:
    sections = _pdf_sections(doc.body) if doc.path.suffix == ".pdf" else _markdown_sections(doc.body)

    chunks = []
    for heading, text in sections:
        # The change log lists old values ("minimum raised from 4.8 to 5.4") that
        # could be retrieved as if they were current, so it is not indexed.
        if heading.lower() == "change log":
            continue
        if doc.path.suffix == ".pdf":
            text = re.split(r"^Change log\s*$", text, flags=re.MULTILINE)[0]
        for piece in _split_long(text.strip(), config.MAX_CHUNK_CHARS):
            # The header line makes the chunk understandable on its own, and
            # gives the embedding the document title and the section name.
            header = f"[{doc.id}] {doc.title} > {heading}"
            chunks.append(Chunk(doc_id=doc.id, section=heading, text=f"{header}\n\n{piece}"))
    return chunks


def build_chunks(docs: dict[str, Doc]) -> list[Chunk]:
    return [c for doc in searchable_docs(docs) for c in chunk_doc(doc)]


if __name__ == "__main__":
    all_docs = load_docs()
    chunks = build_chunks(all_docs)
    print(f"{len(all_docs)} documents loaded, {len(chunks)} chunks from "
          f"{len(searchable_docs(all_docs))} searchable ones\n")
    for d in all_docs.values():
        n = sum(c.doc_id == d.id for c in chunks)
        print(f"{d.id}  {d.status:<10} auth={str(d.authoritative):<5} chunks={n:<2} {d.title}")
