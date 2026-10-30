"""Offline retrieval evals: the real corpus, the real local embedding model.

For each question of the gold set the vector store searches every expected
domain on its own, as the domain agents do, and returns its 5 best chunks.
The last test runs the domain agents themselves (dynamic retrieval).

    questions.yaml --> question, expected domains, clearance
                   --> store.search(question, domain, clearance, limit=5)
                   --> the documents of the hits
                   --> compared with expected_documents and forbidden_documents

The floors are the numbers measured on 2026-10-30 (store 29 of 32 expected
documents, agents 29 of 32, mean reciprocal rank 0.75, expected facts in the
kept chunks 20 of 24). A change that lowers
them fails here.
"""

from pathlib import Path

from rag_system.domain_agents import DomainAgent
from rag_system.messages import AgentTask, Classification, Domain, SubQuery
from rag_system.offline_model import offline_model
from tests.evals.gold_set import QUESTIONS
from tests.evals.measures import (
    agent_counts,
    document_ranks,
    fact_counts,
    found_documents,
    store_counts,
)

ROOT = Path(__file__).parents[2]


def test_retrieval_finds_at_least_29_of_the_32_expected_documents(corpus_store):
    found, expected, missed = store_counts(corpus_store, QUESTIONS)

    assert expected == 32
    assert found >= 29, f"found {found} of {expected}; missed {missed}"


def test_the_expected_documents_rank_high_in_their_domain(corpus_store):
    """Mean reciprocal rank: 1 when every expected document comes first, 1/3
    when each comes third. Random order of 8 documents gives 0.34.

    Measured 2026-10-30: 0.75; first for 19 of 32, top 3 for 30 of 32; the
    worst is CMP-1 for Q03, 6th of the 7 compliance documents it may read.
    """
    ranks = document_ranks(corpus_store, QUESTIONS)

    assert len(ranks) == 32
    assert sum(1 / rank for rank in ranks) / len(ranks) >= 0.75


def test_a_superseded_version_is_never_retrieved_unless_history_is_asked(corpus_store):
    for question in QUESTIONS:
        forbidden = set(question.get("forbidden_documents", []))
        assert not forbidden & found_documents(corpus_store, question), question["id"]


def test_the_cause_buried_in_the_long_incident_review_is_in_the_top_5(corpus_store):
    """Q12: the cause is a moved screen field, told in the middle of TEC-9."""
    question = next(q for q in QUESTIONS if q["id"] == "Q12")

    hits = corpus_store.search(
        question["question"], Domain.TECHNICAL, Classification.INTERNAL, limit=5
    )

    # The words are on two lines in the document, so search for a part.
    assert any("alert reference" in hit.chunk.text for hit in hits)


async def test_the_domain_agents_cite_at_least_29_of_the_32_expected_documents(
    corpus_store,
):
    """Dynamic retrieval end to end: each expected domain's agent, offline model.

    Measured 2026-10-30: 29 of 32. Missed: CMP-1 for Q03, and TEC-2 for Q13 and
    BUS-1 for Q17, because offline nothing asks for superseded versions.
    """
    found, missed = await agent_counts(corpus_store, QUESTIONS)

    assert found >= 29, f"found {found} of 32; missed {missed}"


async def test_the_chunks_the_agents_keep_hold_at_least_20_of_the_24_expected_facts(
    corpus_store,
):
    """Did the fact reach the model? The whole pipeline, offline.

    Measured 2026-10-30: 20 of 24. Missed: Q08 (the BUS-3 chunk scores 0.32
    and is dropped), Q10 (the TEC-7 "Who to call" chunk is not kept), Q13 and
    Q17 (offline nothing asks for superseded versions).
    """
    found, expected, missed = await fact_counts(corpus_store, QUESTIONS)

    assert expected == 24
    assert found >= 20, f"found {found} of {expected}; missed {missed}"


async def test_the_worked_example_in_the_domain_agent_is_still_true(corpus_store):
    """The "Example" comments in DomainAgent._steps follow Q04; keep them true."""
    question = next(q for q in QUESTIONS if q["id"] == "Q04")["question"]

    hits = corpus_store.search(
        question, Domain.TECHNICAL, Classification.INTERNAL, limit=10
    )
    task = AgentTask(
        question=question,
        sub_query=SubQuery(domain=Domain.TECHNICAL, text=question),
        clearance=Classification.INTERNAL,
    )
    answer = await DomainAgent(Domain.TECHNICAL, corpus_store, offline_model()).answer(
        task
    )

    # Step 1: the hits in hybrid order, with their similarity.
    first_seven = [(hit.chunk.id, round(hit.similarity, 2)) for hit in hits[:7]]
    assert first_seven == [
        ("TEC-1#4", 0.33),
        ("TEC-3#5", 0.31),
        ("TEC-3#6", 0.42),
        ("TEC-9#7", 0.31),
        ("TEC-9#4", 0.25),
        ("TEC-3#1", 0.34),
        ("TEC-3#4", 0.31),
    ]
    # Steps 2 and 3: three chunks kept, one claim each.
    claim = answer.claims[1]
    assert claim.text == "Releases happen from Tuesday to Thursday, 09:00 to 15:00."
    # Step 4: the citation built from the chunk id TEC-3#5.
    assert claim.citations[0].model_dump(mode="json") == {
        "doc_id": "TEC-3",
        "chunk_id": "TEC-3#5",
        "title": "Production Release Standard",
        "section": "Release windows",
        "version": 2,
        "effective_date": "2026-02-01",
        "kind": "standard",
        "owner": "Platform Engineering",
    }
    assert len(answer.claims) == 3
    assert round(answer.best_similarity, 2) == 0.42
    assert answer.chunks_read == 3
