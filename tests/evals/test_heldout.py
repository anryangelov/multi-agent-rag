"""Held-out evals: questions written after every threshold was tuned.

    questions.yaml --> the questions with `heldout: true` (Q20-Q54)
                   --> the same offline measures as the tuning evals
                   --> the numbers of their one run on 2026-10-30

Other models wrote the questions from the document titles alone, in two
batches: Q20-Q25, then Q26-Q54. Each batch ran once with the thresholds
frozen. The misses of the first batch were then looked at, without a change
made from them; the second batch was never looked at before its run. The
numbers below are what the runs gave, good or bad:

                          tuning (19 questions)    held-out (35 questions)
    classifier found      26 of 26                 38 of 38
    classifier extra      13                       37
    store, top 5          29 of 32                 30 of 44
    agents cite           29 of 32                 36 of 44
    mean reciprocal rank  0.75                     0.59 (random: 0.34)
    facts in kept chunks  22 of 24                 24 of 37

The gap is in retrieval: on new wording the chunk with the answer often
ranks below the first 8 of its domain (Q21: 22nd, Q22: 31st, Q25: 18th).

A change that lowers these numbers fails here; do not tune a threshold to
these questions, or they stop being held out.
"""

import pytest

from rag_system.messages import Classification, Status
from rag_system.offline_model import offline_model
from rag_system.orchestrator import Orchestrator
from tests.evals.gold_set import HELDOUT
from tests.evals.measures import (
    agent_counts,
    classifier_counts,
    document_ranks,
    fact_counts,
    store_counts,
)

UNANSWERABLE = [q for q in HELDOUT if not q["expected_documents"]]


async def test_the_classifier_finds_every_expected_domain_of_new_questions(
    corpus_store,
):
    found, extra, _, missed = await classifier_counts(corpus_store, HELDOUT)

    assert found == 38, f"missed {missed}"
    assert extra <= 37


def test_retrieval_finds_at_least_30_of_the_44_documents_of_new_questions(
    corpus_store,
):
    found, expected, missed = store_counts(corpus_store, HELDOUT)

    assert expected == 44
    assert found >= 30, f"found {found} of {expected}; missed {missed}"


def test_the_expected_documents_of_new_questions_rank_high_in_their_domain(
    corpus_store,
):
    """Mean reciprocal rank 0.59: first for 19 of 44, top 3 for 29 of 44."""
    ranks = document_ranks(corpus_store, HELDOUT)

    assert sum(1 / rank for rank in ranks) / len(ranks) >= 0.59


async def test_the_domain_agents_cite_at_least_36_of_the_44_documents_of_new_questions(
    corpus_store,
):
    found, missed = await agent_counts(corpus_store, HELDOUT)

    assert found >= 36, f"found {found} of 44; missed {missed}"


async def test_the_kept_chunks_hold_at_least_24_of_the_37_facts_of_new_questions(
    corpus_store,
):
    found, expected, missed = await fact_counts(corpus_store, HELDOUT)

    assert expected == 37
    assert found >= 24, f"found {found} of {expected}; missed {missed}"


@pytest.mark.xfail(
    strict=True,
    reason="known gap offline: for each of the 7 questions some agent finds a "
    "chunk above the 0.4 bar (Q24: business 0.47, compliance 0.46); with a "
    "model, 6 of the 7 end in 'nothing relevant' (test_llm.py)",
)
async def test_no_agent_answers_a_question_that_no_document_answers(corpus_store):
    """Seven questions (Q24, Q32, ...) ask about payroll, meeting rooms,
    travel expenses and the like; no document mentions them."""
    orchestrator = Orchestrator(corpus_store, offline_model())
    assert len(UNANSWERABLE) == 7

    for question in UNANSWERABLE:
        answer = await orchestrator.answer(
            question["question"], Classification.INTERNAL
        )
        assert all(a.status == Status.NOTHING_RELEVANT for a in answer.agent_answers), (
            question["id"]
        )
