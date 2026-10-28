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
        |
    the chunks go to vector_store: VectorStore.add(chunks)

A chunk carries the document's metadata (DocumentInfo), not its whole text,
so a chunk stays small when it is logged or sent anywhere.

A broken file raises IngestionError with the file name and the reason.
"""

import re
from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from rag_system.messages import Citation, Classification, Domain, Kind

SECTION_LIMIT = 250  # words; a longer section is cut at paragraphs
PIECE_TARGET = 150  # words; paragraphs are packed into pieces up to this size

_FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_SECTION_START = re.compile(r"(?m)^(?=## )")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class DocumentInfo(BaseModel):
    """Everything about a document except its text: what a citation needs.

    A newer version names the version it replaces in `supersedes` (TEC-3
    supersedes TEC-2). That link is the only record of it: the store treats
    a document that another document supersedes as history.
    """

    # extra="forbid": a misspelt or retired field in a file fails loudly
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    domain: Domain
    kind: Kind
    version: int
    effective_date: date
    supersedes: str | None = None
    classification: Classification
    owner: str


class Document(DocumentInfo):
    """One file of the corpus: its metadata and its text."""

    body: str

    def info(self) -> DocumentInfo:
        return DocumentInfo(**self.model_dump(exclude={"body"}))


class Chunk(BaseModel):
    """One piece of a document: what is embedded, searched and cited."""

    model_config = ConfigDict(frozen=True)

    id: str  # "TEC-3#2": the document id and the chunk's position in it
    document: DocumentInfo
    section: str | None  # the "## " heading; None for text outside a section
    text: str  # the document title, the heading, then the piece itself

    def citation(self) -> Citation:
        """How an answer points back to this chunk: document and section."""
        return Citation(
            doc_id=self.document.id,
            title=self.document.title,
            section=self.section,
            version=self.document.version,
            effective_date=self.document.effective_date,
            kind=self.document.kind,
            owner=self.document.owner,
        )


class IngestionError(ValueError):
    """A file that cannot become a Document; the message names the file."""


def load_documents(folder: Path) -> list[Document]:
    """Read every Markdown file under `folder`, sorted by path."""
    documents = []
    for path in sorted(folder.rglob("*.md")):
        documents.append(_read(path))
    return documents


def _read(path: Path) -> Document:
    match = _FRONT_MATTER.match(path.read_text())
    if match is None:
        raise IngestionError(f"{path.name}: no front matter between two '---' lines")
    metadata = yaml.safe_load(match.group(1))
    body = match.group(2)
    try:
        return Document(**metadata, body=body)
    except ValidationError as error:
        reasons = []
        for problem in error.errors():
            field = ".".join(str(part) for part in problem["loc"])
            reasons.append(f"{field}: {problem['msg']}")
        raise IngestionError(f"{path.name}: {'; '.join(reasons)}") from error


def chunk_document(document: Document) -> list[Chunk]:
    """Cut a document into chunks; each chunk starts with the document title.

    1. Cut at `##` sections; text before the first one is its own part.
    2. A part over SECTION_LIMIT words is cut at paragraphs into pieces of
       up to PIECE_TARGET words; every piece repeats the section heading.
    """
    info = document.info()
    chunks = []
    for part in _SECTION_START.split(document.body):
        part = part.strip()
        if not part:
            continue
        heading, section, content = _split_heading(part)
        for piece in _pieces(content):
            text_parts = [document.title]
            if heading is not None:
                text_parts.append(heading)
            text_parts.append(piece)
            chunk = Chunk(
                id=f"{document.id}#{len(chunks) + 1}",
                document=info,
                section=section,
                text="\n\n".join(text_parts),
            )
            chunks.append(chunk)
    return chunks


def _split_heading(part: str) -> tuple[str | None, str | None, str]:
    """Return the `##` heading line, the section name and the rest."""
    first_line, _, rest = part.partition("\n")
    if not first_line.startswith("## "):
        return None, None, part
    section = first_line.removeprefix("## ").strip()
    return first_line, section, rest.strip()


def _pieces(content: str) -> list[str]:
    """Pack paragraphs (or, for an over-long paragraph, its sentences) into pieces."""
    if _word_count(content) <= SECTION_LIMIT:
        return [content]
    pieces = []
    current = ""
    for unit, separator in _units(content):
        if current and _word_count(current) + _word_count(unit) > PIECE_TARGET:
            pieces.append(current)
            current = ""
        if current:
            current = current + separator + unit
        else:
            current = unit
    if current:
        pieces.append(current)
    return pieces


def _units(content: str) -> list[tuple[str, str]]:
    """The pieces are built from: paragraphs, separated by a blank line.

    A paragraph over SECTION_LIMIT words is replaced by its sentences,
    separated by a space, so no piece cuts a sentence in half.
    """
    units = []
    for paragraph in content.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if _word_count(paragraph) <= SECTION_LIMIT:
            units.append((paragraph, "\n\n"))
            continue
        sentences = _SENTENCE_END.split(paragraph)
        units.append((sentences[0], "\n\n"))
        for sentence in sentences[1:]:
            units.append((sentence, " "))
    return units


def _word_count(text: str) -> int:
    return len(text.split())
