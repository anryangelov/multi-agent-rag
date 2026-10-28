"""Offline retrieval evals: the real corpus, the real local embedding model.

For each question of the gold set the vector store searches every expected
domain on its own, as the domain agents do, and returns its 5 best chunks.

    questions.yaml --> question, expected domains, clearance
                   --> store.search(question, domain, clearance, limit=5)
                   --> the documents of the hits
                   --> compared with expected_documents and forbidden_documents

The floors are the numbers measured on 2026-10-28 (22 of 25 expected
documents). A change that lowers them fails here.
"""

from pathlib import Path

import pytest
import yaml

from rag_system.config import Settings, build_embedder
from rag_system.ingestion import chunk_document, load_documents
from rag_system.messages import Classification, Domain
from rag_system.vector_store import InMemoryVectorStore

ROOT = Path(__file__).parents[2]
QUESTIONS = yaml.safe_load((Path(__file__).parent / "questions.yaml").read_text())
LIMIT = 5


@pytest.fixture(scope="module")
def store() -> InMemoryVectorStore:
    vector_store = InMemoryVectorStore(build_embedder(Settings(_env_file=None)))
    for document in load_documents(ROOT / "data"):
        vector_store.add(chunk_document(document))
    return vector_store


def found_documents(store: InMemoryVectorStore, question: dict) -> set[str]:
    """The documents of the hits in every expected domain of the question."""
    found = set()
    for domain in question["expected_domains"]:
        hits = store.search(
            question["question"],
            Domain(domain),
            Classification(question.get("clearance", "internal")),
            limit=LIMIT,
            include_superseded=question.get("include_superseded", False),
        )
        found |= {hit.chunk.document.id for hit in hits}
    return found


def test_retrieval_finds_at_least_22_of_the_25_expected_documents(store):
    found, expected, missed = 0, 0, []
    for question in QUESTIONS:
        documents = found_documents(store, question)
        for doc_id in question["expected_documents"]:
            expected += 1
            if doc_id in documents:
                found += 1
            else:
                missed.append(f"{question['id']}: {doc_id}")

    assert expected == 25
    assert found >= 22, f"found {found} of {expected}; missed {missed}"


def test_a_superseded_version_is_never_retrieved_unless_history_is_asked(store):
    for question in QUESTIONS:
        forbidden = set(question.get("forbidden_documents", []))
        assert not forbidden & found_documents(store, question), question["id"]


def test_the_cause_buried_in_the_long_incident_review_is_in_the_top_5(store):
    """Q12: the cause is a moved screen field, told in the middle of TEC-9."""
    question = next(q for q in QUESTIONS if q["id"] == "Q12")

    hits = store.search(
        question["question"], Domain.TECHNICAL, Classification.INTERNAL, limit=LIMIT
    )

    # The words are on two lines in the document, so search for a part.
    assert any("alert reference" in hit.chunk.text for hit in hits)
