"""How do documents enter the system? They are read, checked and cut into chunks.

    data/<domain>/<ID>-<slug>.md
        |
    1. load_documents: split the YAML front matter from the text and check
       the metadata                                   --> Document
        |
    2. chunk_document: cut at "## " sections; a section over 250 words, or
       a document without headings, is cut at paragraphs (an over-long
       paragraph at sentences) into pieces of up to 150 words; every chunk
       starts with the document title                 --> Chunk, Chunk, ...

A broken file raises IngestionError with the file name and the reason.
"""

import re
from datetime import date
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from rag_system.messages import Classification, Domain, Kind

_FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


class DocumentStatus(StrEnum):
    CURRENT = "current"
    SUPERSEDED = "superseded"


class Document(BaseModel):
    """One file of the corpus: its metadata and its text."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    domain: Domain
    kind: Kind
    version: int
    effective_date: date
    status: DocumentStatus
    supersedes: str | None = None
    classification: Classification
    owner: str
    body: str


class IngestionError(ValueError):
    """A file that cannot become a Document; the message names the file."""


def load_documents(folder: Path) -> list[Document]:
    """Read every Markdown file under `folder`, sorted by path."""
    return [_read(path) for path in sorted(folder.rglob("*.md"))]


def _read(path: Path) -> Document:
    match = _FRONT_MATTER.match(path.read_text())
    if not match:
        raise IngestionError(f"{path.name}: no front matter between two '---' lines")
    metadata = yaml.safe_load(match.group(1))
    try:
        return Document(**metadata, body=match.group(2))
    except ValidationError as error:
        reasons = "; ".join(
            f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()
        )
        raise IngestionError(f"{path.name}: {reasons}") from error


class Chunk(BaseModel):
    """One piece of a document: what is embedded, searched and cited."""

    model_config = ConfigDict(frozen=True)

    id: str
    document: Document
    section: str | None
    text: str


_SECTION = re.compile(r"(?m)^(?=## )")
SECTION_LIMIT = 250  # words; a longer section is cut at paragraphs
PIECE_TARGET = 150  # words; paragraphs are packed into pieces up to this size


def chunk_document(document: Document) -> list[Chunk]:
    """Cut a document into chunks; each chunk starts with the document title.

    1. Cut at `##` sections; text before the first one is its own part.
    2. A part over SECTION_LIMIT words is cut at paragraphs into pieces of
       up to PIECE_TARGET words; every piece repeats the section heading.
    """
    chunks = []
    for part in _SECTION.split(document.body):
        part = part.strip()
        if not part:
            continue
        heading, section, content = _split_heading(part)
        for piece in _pieces(content):
            text = "\n\n".join(x for x in (document.title, heading, piece) if x)
            chunks.append(
                Chunk(
                    id=f"{document.id}#{len(chunks) + 1}",
                    document=document,
                    section=section,
                    text=text,
                )
            )
    return chunks


def _split_heading(part: str) -> tuple[str | None, str | None, str]:
    """Return the `##` heading line, the section name and the rest."""
    first, _, rest = part.partition("\n")
    if first.startswith("## "):
        return first, first.removeprefix("## ").strip(), rest.strip()
    return None, None, part


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _pieces(content: str) -> list[str]:
    """Pack paragraphs (or, for an over-long paragraph, its sentences) into pieces."""
    if _words(content) <= SECTION_LIMIT:
        return [content]
    pieces, current = [], ""
    for unit, joiner in _units(content):
        if current and _words(current) + _words(unit) > PIECE_TARGET:
            pieces.append(current)
            current = ""
        current = f"{current}{joiner}{unit}" if current else unit
    if current:
        pieces.append(current)
    return pieces


def _units(content: str) -> list[tuple[str, str]]:
    """Paragraphs, joined by a blank line; a paragraph over SECTION_LIMIT words
    becomes its sentences, joined by a space."""
    units = []
    for paragraph in (p.strip() for p in content.split("\n\n")):
        if not paragraph:
            continue
        if _words(paragraph) <= SECTION_LIMIT:
            units.append((paragraph, "\n\n"))
        else:
            sentences = _SENTENCE_END.split(paragraph)
            units.append((sentences[0], "\n\n"))
            units.extend((sentence, " ") for sentence in sentences[1:])
    return units


def _words(text: str) -> int:
    return len(text.split())
