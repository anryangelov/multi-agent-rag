"""Documents enter the system: they are read, checked and cut into chunks."""

from datetime import date
from pathlib import Path

import pytest

from rag_system.ingestion import (
    SECTION_LIMIT,
    Document,
    IngestionError,
    chunk_document,
    load_documents,
)
from rag_system.messages import Classification, Domain, Kind

DATA = Path(__file__).parents[2] / "data"


def test_the_corpus_loads_with_its_metadata():
    documents = {d.id: d for d in load_documents(DATA)}

    assert len(documents) == 26
    newer = documents["TEC-3"]
    assert newer.domain is Domain.TECHNICAL
    assert newer.kind is Kind.STANDARD
    assert newer.version == 2
    assert newer.effective_date == date(2026, 2, 1)
    assert newer.supersedes == "TEC-2"
    assert documents["BUS-8"].classification is Classification.CONFIDENTIAL
    assert newer.body.startswith("# Production Release Standard (version 2)")


VALID = """---
id: TEC-1
title: A title
domain: technical
kind: guide
version: 1
effective_date: 2026-01-01
status: current
classification: internal
owner: Platform Engineering
---
# A title
"""


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("# No front matter at all\n", "front matter"),
        (VALID.replace("owner: Platform Engineering\n", ""), "owner"),
        (
            VALID.replace("classification: internal", "classification: secret"),
            "classification",
        ),
    ],
)
def test_a_broken_file_fails_with_its_name_and_the_reason(tmp_path, content, reason):
    (tmp_path / "TEC-1-broken.md").write_text(content)
    with pytest.raises(IngestionError, match=rf"TEC-1-broken\.md.*{reason}"):
        load_documents(tmp_path)


def document(body: str) -> Document:
    return Document(
        id="TEC-3",
        title="Production Release Standard",
        domain=Domain.TECHNICAL,
        kind=Kind.STANDARD,
        version=2,
        effective_date=date(2026, 2, 1),
        status="current",
        classification=Classification.INTERNAL,
        owner="Platform Engineering",
        body=body,
    )


def test_each_section_becomes_a_chunk_that_starts_with_the_document_title():
    chunks = chunk_document(
        document(
            "## Approvals\n\nTwo approvers.\n\n## Rollback\n\nWithin 15 minutes.\n"
        )
    )

    assert [c.section for c in chunks] == ["Approvals", "Rollback"]
    assert (
        chunks[0].text
        == "Production Release Standard\n\n## Approvals\n\nTwo approvers."
    )
    assert all(c.document.id == "TEC-3" for c in chunks)


def test_text_before_the_first_section_is_a_chunk_without_a_section():
    chunks = chunk_document(
        document(
            "# Production Release Standard\n\n"
            "This standard applies.\n\n"
            "## Approvals\n\nTwo.\n"
        )
    )

    assert [c.section for c in chunks] == [None, "Approvals"]
    assert "This standard applies." in chunks[0].text


def paragraph(n: int, words: int = 60) -> str:
    return " ".join([f"p{n}w{i}" for i in range(words)])


def test_a_long_section_is_cut_at_paragraphs_and_keeps_its_name():
    paragraphs = [paragraph(n) for n in range(6)]  # 6 x 60 = 360 words
    chunks = chunk_document(document("## Approvals\n\n" + "\n\n".join(paragraphs)))

    assert len(chunks) == 3  # 120 + 120 + 120: a fourth paragraph would pass 150
    assert all(c.section == "Approvals" for c in chunks)
    assert all(
        c.text.startswith("Production Release Standard\n\n## Approvals") for c in chunks
    )
    for p in paragraphs:
        assert sum(p in c.text for c in chunks) == 1


def test_a_long_document_without_headings_is_cut_at_paragraphs():
    minutes = next(d for d in load_documents(DATA) if d.id == "BUS-9")

    chunks = chunk_document(minutes)

    assert len(chunks) > 5
    assert all(c.section is None for c in chunks)
    assert all(len(c.text.split()) <= SECTION_LIMIT for c in chunks)
    assert any("approved the\nfunding of a second RPA robot" in c.text for c in chunks)


def test_a_single_paragraph_longer_than_the_limit_is_cut_at_sentences():
    sentences = [f"Sentence {n} has exactly eight words in it." for n in range(50)]
    chunks = chunk_document(document(" ".join(sentences)))  # 400 words, one paragraph

    assert len(chunks) > 1
    assert all(len(c.text.split()) <= SECTION_LIMIT for c in chunks)
    assert all(c.text.rstrip().endswith(".") for c in chunks)  # no sentence cut in half


def test_chunk_ids_are_unique_and_the_same_on_every_run():
    first = [c.id for d in load_documents(DATA) for c in chunk_document(d)]
    second = [c.id for d in load_documents(DATA) for c in chunk_document(d)]

    assert first == second
    assert len(first) == len(set(first))
    assert "TEC-3#1" in first


def test_a_chunk_carries_the_documents_metadata_but_not_its_whole_text():
    minutes = next(d for d in load_documents(DATA) if d.id == "BUS-9")

    chunks = chunk_document(minutes)

    assert chunks[0].document.id == "BUS-9"
    assert chunks[0].document.classification is Classification.INTERNAL
    assert "body" not in chunks[0].model_dump()["document"]
    assert len(chunks[0].model_dump_json()) < 3000
