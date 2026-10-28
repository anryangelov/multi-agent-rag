"""Feedback on the sources of an answer changes what is retrieved next time."""

import random
from datetime import date

import pytest

from rag_system.domain_agents import DomainAgent
from rag_system.ingestion import Document, chunk_document
from rag_system.learning import ChunkWeights, Rating, SimulatedUser
from rag_system.messages import (
    AgentTask,
    Citation,
    Classification,
    Domain,
    FinalAnswer,
    Kind,
    Plan,
    SubQuery,
)
from rag_system.offline_model import offline_model
from rag_system.vector_store import InMemoryVectorStore
from tests.fakes import WordHashEmbedder

DEPLOY = "How do I deploy a new service?"


def test_a_useful_rating_raises_a_weight_and_a_useless_one_lowers_it():
    weights = ChunkWeights(WordHashEmbedder())

    weights.apply(DEPLOY, [Rating(chunk_id="TEC-1#2", useful=True)])
    weights.apply(DEPLOY, [Rating(chunk_id="TEC-6#5", useful=False)])

    now = weights.for_question(DEPLOY)
    assert now.weight("TEC-1#2") == pytest.approx(1.25)
    assert now.weight("TEC-6#5") == pytest.approx(0.8)
    assert now.weight("CMP-4#1") == 1.0  # never rated


def test_a_rating_counts_for_similar_questions_only():
    weights = ChunkWeights(WordHashEmbedder())
    weights.apply(DEPLOY, [Rating(chunk_id="TEC-6#5", useful=False)])

    similar = weights.for_question("How do I deploy a service?")
    unrelated = weights.for_question("Who approves the budget of a team?")

    assert similar.weight("TEC-6#5") == pytest.approx(0.8)
    assert unrelated.weight("TEC-6#5") == 1.0


def test_a_weight_stays_between_half_and_double():
    weights = ChunkWeights(WordHashEmbedder())

    for _ in range(10):
        weights.apply(DEPLOY, [Rating(chunk_id="TEC-1#2", useful=True)])
        weights.apply(DEPLOY, [Rating(chunk_id="TEC-6#5", useful=False)])

    now = weights.for_question(DEPLOY)
    assert now.weight("TEC-1#2") == 2.0
    assert now.weight("TEC-6#5") == 0.5


def test_every_rating_is_recorded_and_a_reset_forgets_them():
    weights = ChunkWeights(WordHashEmbedder())
    weights.apply(DEPLOY, [Rating(chunk_id="TEC-6#5", useful=False)])

    [record] = weights.history
    assert (record.question, record.chunk_id, record.useful) == (
        DEPLOY,
        "TEC-6#5",
        False,
    )

    weights.reset()
    assert weights.for_question(DEPLOY).weight("TEC-6#5") == 1.0
    assert weights.history == []


def source(chunk_id: str) -> Citation:
    return Citation(
        doc_id=chunk_id.split("#")[0],
        chunk_id=chunk_id,
        title="A title",
        section=None,
        version=1,
        effective_date=date(2026, 1, 1),
        kind=Kind.GUIDE,
        owner="Platform Engineering",
    )


def answer_citing(*chunk_ids: str) -> FinalAnswer:
    return FinalAnswer(
        question="How do I deploy?",
        plan=Plan(sub_queries=[SubQuery(domain=Domain.TECHNICAL, text="?")]),
        agent_answers=[],
        text="...",
        sources=[source(chunk_id) for chunk_id in chunk_ids],
    )


def test_the_simulated_user_finds_a_source_useful_when_its_document_is_expected():
    user = SimulatedUser(random.Random(42), wrong_share=0.0)

    ratings = user.rate(answer_citing("TEC-1#2", "TEC-6#5"), expected={"TEC-1"})

    assert ratings == [
        Rating(chunk_id="TEC-1#2", useful=True),
        Rating(chunk_id="TEC-6#5", useful=False),
    ]


def test_the_simulated_user_is_sometimes_wrong_like_a_real_one():
    always_wrong = SimulatedUser(random.Random(42), wrong_share=1.0)

    ratings = always_wrong.rate(answer_citing("TEC-1#2"), expected={"TEC-1"})

    assert ratings == [Rating(chunk_id="TEC-1#2", useful=False)]


def document(doc_id: str, body: str) -> Document:
    return Document(
        id=doc_id,
        title=f"Document {doc_id}",
        domain=Domain.TECHNICAL,
        kind=Kind.GUIDE,
        version=1,
        effective_date=date(2026, 1, 1),
        classification=Classification.INTERNAL,
        owner="Platform Engineering",
        body=body,
    )


def cited(answer) -> list[str]:
    return [c.chunk_id for claim in answer.claims for c in claim.citations]


async def test_a_chunk_rated_useless_falls_out_of_what_the_agent_keeps():
    store = InMemoryVectorStore(WordHashEmbedder())
    for doc_id in ("TEC-1", "TEC-2", "TEC-3", "TEC-4"):
        store.add(chunk_document(document(doc_id, f"Deploy a service, step {doc_id}.")))
    weights = ChunkWeights(WordHashEmbedder())
    agent = DomainAgent(Domain.TECHNICAL, store, offline_model(), weights=weights)
    question = "Deploy a service"
    task = AgentTask(
        question=question,
        sub_query=SubQuery(domain=Domain.TECHNICAL, text=question),
        clearance=Classification.INTERNAL,
    )
    before = cited(await agent.answer(task))

    for _ in range(3):
        weights.apply(question, [Rating(chunk_id="TEC-4#1", useful=False)])
    after = cited(await agent.answer(task))

    assert "TEC-4#1" in before
    assert "TEC-4#1" not in after
