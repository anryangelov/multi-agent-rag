"""Held-out evals: questions written after every threshold was tuned.

    questions.yaml --> the questions with `heldout: true` (Q20-Q25)
                   --> the same offline measures as the tuning evals
                   --> the numbers of the one run on 2026-10-30

A separate model wrote the questions from the document titles alone, and
they ran once with the thresholds frozen (0.4 to keep a chunk, top 8 for the
classifier). The numbers below are what that run gave, good or bad:

                          tuning (19 questions)    held-out (6 questions)
    classifier found      26 of 26                 7 of 7
    classifier extra      13                       7
    store, top 5          29 of 32                 8 of 9 (missed Q25 CMP-1)
    agents cite           29 of 32                 9 of 9

A change that lowers them fails here; do not tune a threshold to these
questions, or they stop being held out.
"""

import pytest

from rag_system.messages import Classification, Status
from rag_system.offline_model import offline_model
from rag_system.orchestrator import Orchestrator
from tests.evals.gold_set import HELDOUT
from tests.evals.measures import agent_counts, classifier_counts, store_counts


async def test_the_classifier_finds_every_expected_domain_of_new_questions(
    corpus_store,
):
    found, extra, _, missed = await classifier_counts(corpus_store, HELDOUT)

    assert found == 7, f"missed {missed}"
    assert extra <= 7


def test_retrieval_finds_at_least_8_of_the_9_expected_documents_of_new_questions(
    corpus_store,
):
    found, expected, missed = store_counts(corpus_store, HELDOUT)

    assert expected == 9
    assert found >= 8, f"found {found} of {expected}; missed {missed}"


async def test_the_domain_agents_cite_all_9_expected_documents_of_new_questions(
    corpus_store,
):
    found, missed = await agent_counts(corpus_store, HELDOUT)

    assert found == 9, f"found {found} of 9; missed {missed}"


@pytest.mark.xfail(
    strict=True,
    reason="known gap: offline, the best chunks of business and compliance "
    "score 0.47 and 0.46, above the 0.4 bar, so both agents answer",
)
async def test_no_agent_answers_a_question_that_no_document_answers(corpus_store):
    """Q24 asks about staff bonuses and Payroll; no document mentions them."""
    question = next(q for q in HELDOUT if q["id"] == "Q24")

    answer = await Orchestrator(corpus_store, offline_model()).answer(
        question["question"], Classification.INTERNAL
    )

    assert all(a.status == Status.NOTHING_RELEVANT for a in answer.agent_answers)
