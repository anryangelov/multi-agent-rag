"""Offline classifier evals: the real corpus, the real local embedding model.

    questions.yaml --> question, clearance
                   --> QueryClassifier.classify (offline model)
                   --> the domains of the plan
                   --> compared with expected_domains

Measured on 2026-10-28: all 20 expected domains found, 8 extra, 8 of 14
plans exact. A change that finds fewer or adds more fails here.
"""

from pathlib import Path

import yaml

from rag_system.messages import Classification, Domain
from rag_system.offline_model import offline_model
from rag_system.query_classifier import QueryClassifier
from rag_system.vector_store import Ranking

ROOT = Path(__file__).parents[2]
QUESTIONS = yaml.safe_load((Path(__file__).parent / "questions.yaml").read_text())


async def test_the_classifier_finds_every_expected_domain_with_at_most_8_extra(
    corpus_store,
):
    classifier = QueryClassifier(corpus_store, offline_model())
    found, extra, missed = 0, 0, []
    for question in QUESTIONS:
        plan = await classifier.classify(
            question["question"], Classification(question.get("clearance", "internal"))
        )
        asked = {sub_query.domain for sub_query in plan.sub_queries}
        expected = {Domain(domain) for domain in question["expected_domains"]}
        found += len(asked & expected)
        extra += len(asked - expected)
        missed += [f"{question['id']}: {domain}" for domain in expected - asked]

    assert found == 20, f"missed {missed}"
    assert extra <= 8


async def test_the_worked_example_in_the_classifier_is_still_true(corpus_store):
    """The "Example" comments in QueryClassifier.classify follow Q01."""
    question = next(q for q in QUESTIONS if q["id"] == "Q01")["question"]

    hits = corpus_store.search(
        question,
        domain=None,
        clearance=Classification.INTERNAL,
        limit=8,
        ranking=Ranking.EMBEDDING,
    )
    plan = await QueryClassifier(corpus_store, offline_model()).classify(
        question, Classification.INTERNAL
    )

    assert [(hit.chunk.id, round(hit.similarity, 2)) for hit in hits] == [
        ("TEC-1#1", 0.75),
        ("CMP-4#1", 0.6),
        ("TEC-3#4", 0.59),
        ("TEC-1#2", 0.58),
        ("TEC-1#5", 0.54),
        ("TEC-1#3", 0.54),
        ("CMP-4#2", 0.53),
        ("TEC-1#4", 0.53),
    ]
    assert [(sub.domain, sub.text) for sub in plan.sub_queries] == [
        (Domain.TECHNICAL, question),
        (Domain.COMPLIANCE, question),
    ]
