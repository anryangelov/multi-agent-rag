"""The vector store finds chunks of one domain that the caller may read."""

from datetime import date

from rag_system.ingestion import Chunk, Document
from rag_system.messages import Classification, Domain, Kind
from rag_system.vector_store import InMemoryVectorStore, Ranking
from tests.fakes import BlindEmbedder, WordHashEmbedder


def chunk(
    doc_id: str,
    text: str,
    domain: Domain = Domain.TECHNICAL,
    classification: Classification = Classification.INTERNAL,
    supersedes: str | None = None,
) -> Chunk:
    document = Document(
        id=doc_id,
        title=f"Title of {doc_id}",
        domain=domain,
        kind=Kind.GUIDE,
        version=1,
        effective_date=date(2026, 1, 1),
        supersedes=supersedes,
        classification=classification,
        owner="Platform Engineering",
        body=text,
    )
    return Chunk(id=f"{doc_id}#1", document=document.info(), section=None, text=text)


def store(*chunks: Chunk) -> InMemoryVectorStore:
    vector_store = InMemoryVectorStore(WordHashEmbedder())
    vector_store.add(list(chunks))
    return vector_store


def test_search_returns_only_chunks_of_the_asked_domain():
    s = store(
        chunk("TEC-1", "release approvals need two approvers"),
        chunk("BUS-1", "release approvals by the department head", Domain.BUSINESS),
    )

    hits = s.search(
        "release approvals", Domain.BUSINESS, Classification.INTERNAL, limit=5
    )

    assert [h.chunk.document.id for h in hits] == ["BUS-1"]


def test_search_never_returns_a_chunk_above_the_callers_clearance():
    s = store(
        chunk(
            "CMP-2", "rules for customer data and the cloud model", Domain.COMPLIANCE
        ),
        chunk(
            "CMP-8",
            "incident: customer data sent to the cloud model",
            Domain.COMPLIANCE,
            Classification.CONFIDENTIAL,
        ),
    )

    internal = s.search(
        "customer data cloud model", Domain.COMPLIANCE, Classification.INTERNAL, 5
    )
    confidential = s.search(
        "customer data cloud model", Domain.COMPLIANCE, Classification.CONFIDENTIAL, 5
    )

    assert {h.chunk.document.id for h in internal} == {"CMP-2"}
    assert {h.chunk.document.id for h in confidential} == {"CMP-2", "CMP-8"}


def test_exact_words_find_a_chunk_that_the_embeddings_cannot_tell_apart():
    s = InMemoryVectorStore(BlindEmbedder())
    s.add(
        [
            chunk("TEC-7", "the on-call engineer pauses the workflow"),
            chunk("TEC-6", "alerts page the owning team"),
            chunk("TEC-9", "the robot did not find the alert reference field"),
        ]
    )

    hits = s.search(
        "alert reference field", Domain.TECHNICAL, Classification.INTERNAL, 3
    )

    assert hits[0].chunk.document.id == "TEC-9"


def test_search_returns_at_most_limit_hits_with_their_similarity():
    s = store(*(chunk(f"TEC-{n}", f"release step {n}") for n in range(1, 6)))

    hits = s.search("release step", Domain.TECHNICAL, Classification.INTERNAL, 2)

    assert len(hits) == 2
    assert all(0 < h.similarity <= 1 for h in hits)


def test_chunks_added_later_are_found_like_the_first_ones():
    s = store(chunk("TEC-1", "deploying a new microservice"))
    s.add([chunk("TEC-10", "rotating the vault secrets every quarter")])

    hits = s.search("vault secrets", Domain.TECHNICAL, Classification.INTERNAL, 1)

    assert hits[0].chunk.document.id == "TEC-10"


def test_the_index_names_the_model_that_built_it():
    assert store().model == "test:word-hash-64"


def test_an_empty_index_or_an_empty_query_finds_nothing():
    assert (
        store().search("anything", Domain.TECHNICAL, Classification.INTERNAL, 5) == []
    )
    s = store(chunk("TEC-1", "deploying a new microservice"))
    assert s.search("  ", Domain.TECHNICAL, Classification.INTERNAL, 5) == []


def test_a_superseded_version_is_not_searched_unless_asked_for():
    s = store(
        chunk("TEC-2", "a production release needs one approver"),
        chunk("TEC-3", "a production release needs two approvers", supersedes="TEC-2"),
    )

    today = s.search("release approver", Domain.TECHNICAL, Classification.INTERNAL, 5)
    history = s.search(
        "release approver",
        Domain.TECHNICAL,
        Classification.INTERNAL,
        5,
        include_superseded=True,
    )

    assert {h.chunk.document.id for h in today} == {"TEC-3"}
    assert {h.chunk.document.id for h in history} == {"TEC-2", "TEC-3"}


def test_a_new_version_added_later_retires_the_old_one():
    """A knowledge update: the new version names the old one in `supersedes`."""
    s = store(chunk("TEC-3", "a production release needs two approvers"))
    s.add(
        [
            chunk(
                "TEC-10",
                "a production release needs three approvers",
                supersedes="TEC-3",
            )
        ]
    )

    hits = s.search("release approvers", Domain.TECHNICAL, Classification.INTERNAL, 5)

    assert [h.chunk.document.id for h in hits] == ["TEC-10"]


def test_search_with_no_domain_searches_every_domain_the_caller_may_read():
    s = store(
        chunk("TEC-1", "release approvals need two approvers"),
        chunk("BUS-1", "release approvals by the department head", Domain.BUSINESS),
        chunk(
            "CMP-8",
            "release approvals were skipped in the incident",
            Domain.COMPLIANCE,
            Classification.CONFIDENTIAL,
        ),
    )

    hits = s.search(
        "release approvals", domain=None, clearance=Classification.INTERNAL, limit=5
    )

    assert {h.chunk.document.id for h in hits} == {"TEC-1", "BUS-1"}


def test_ranking_by_meaning_orders_hits_from_most_to_least_similar():
    s = store(
        chunk("TEC-1", "release approvals need two approvers"),
        chunk("TEC-2", "release release release windows"),
        chunk("TEC-3", "approvers sign the release request"),
        chunk("TEC-4", "two approvers for every production release"),
    )

    hits = s.search(
        "how many approvers does a release need",
        Domain.TECHNICAL,
        Classification.INTERNAL,
        limit=4,
        ranking=Ranking.EMBEDDING,
    )

    similarities = [h.similarity for h in hits]
    assert similarities == sorted(similarities, reverse=True)
    assert len(hits) == 4
