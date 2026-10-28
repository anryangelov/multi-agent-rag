"""Offline retrieval evals: the real corpus, the real local embedding model.

For each question of the gold set the vector store searches every expected
domain on its own, as the domain agents do, and returns its 5 best chunks.
The last test runs the domain agents themselves (dynamic retrieval).

    questions.yaml --> question, expected domains, clearance
                   --> store.search(question, domain, clearance, limit=5)
                   --> the documents of the hits
                   --> compared with expected_documents and forbidden_documents

The floors are the numbers measured on 2026-10-28 (store 26 of 29 expected
documents, agents 27 of 29). A change that lowers them fails here.
"""

from pathlib import Path

import yaml

from rag_system.domain_agents import DomainAgent
from rag_system.messages import AgentTask, Classification, Domain, SubQuery
from rag_system.offline_model import offline_model
from rag_system.vector_store import InMemoryVectorStore

ROOT = Path(__file__).parents[2]
QUESTIONS = yaml.safe_load((Path(__file__).parent / "questions.yaml").read_text())
LIMIT = 5


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


def test_retrieval_finds_at_least_26_of_the_29_expected_documents(corpus_store):
    found, expected, missed = 0, 0, []
    for question in QUESTIONS:
        documents = found_documents(corpus_store, question)
        for doc_id in question["expected_documents"]:
            expected += 1
            if doc_id in documents:
                found += 1
            else:
                missed.append(f"{question['id']}: {doc_id}")

    assert expected == 29
    assert found >= 26, f"found {found} of {expected}; missed {missed}"


def test_a_superseded_version_is_never_retrieved_unless_history_is_asked(corpus_store):
    for question in QUESTIONS:
        forbidden = set(question.get("forbidden_documents", []))
        assert not forbidden & found_documents(corpus_store, question), question["id"]


def test_the_cause_buried_in_the_long_incident_review_is_in_the_top_5(corpus_store):
    """Q12: the cause is a moved screen field, told in the middle of TEC-9."""
    question = next(q for q in QUESTIONS if q["id"] == "Q12")

    hits = corpus_store.search(
        question["question"], Domain.TECHNICAL, Classification.INTERNAL, limit=LIMIT
    )

    # The words are on two lines in the document, so search for a part.
    assert any("alert reference" in hit.chunk.text for hit in hits)


async def test_the_domain_agents_cite_at_least_27_of_the_29_expected_documents(
    corpus_store,
):
    """Dynamic retrieval end to end: each expected domain's agent, offline model.

    Measured 2026-10-28: 27 of 29. Missed: CMP-1 for Q03, and TEC-2 for Q13,
    because nothing in the pipeline asks for superseded versions yet.
    """
    agents = {
        domain: DomainAgent(domain, corpus_store, offline_model()) for domain in Domain
    }
    found, missed = 0, []
    for question in QUESTIONS:
        cited = set()
        for domain in question["expected_domains"]:
            task = AgentTask(
                question=question["question"],
                sub_query=SubQuery(domain=domain, text=question["question"]),
                clearance=question.get("clearance", "internal"),
            )
            answer = await agents[Domain(domain)].answer(task)
            for claim in answer.claims:
                cited |= {citation.doc_id for citation in claim.citations}
        for doc_id in question["expected_documents"]:
            if doc_id in cited:
                found += 1
            else:
                missed.append(f"{question['id']}: {doc_id}")

    assert found >= 27, f"found {found} of 29; missed {missed}"


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
        "title": "Production Release Standard",
        "section": "Release windows",
        "version": 2,
        "effective_date": "2026-02-01",
        "kind": "standard",
    }
    assert len(answer.claims) == 3
    assert round(answer.best_similarity, 2) == 0.42
