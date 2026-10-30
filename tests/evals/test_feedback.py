"""Offline learning evals: feedback from a simulated user, end to end.

    questions.yaml --> Orchestrator.answer (offline model, learned weights)
                   --> SimulatedUser rates each source: useful when its
                       document is expected; wrong in 10% of the ratings
                   --> ChunkWeights.apply, three rounds
                   --> the same questions, their paraphrases and questions
                       that received no feedback, answered again

Measured on 2026-10-30 (found expected documents, sources from documents
that are not expected answers):
    same questions          29 of 32, 145 off-target  ->  29 of 32, 33
    paraphrases             28 of 32, 209 off-target  ->  28 of 32, 155
    questions not rated     14 of 14,  38 off-target  ->  14 of 14, 38
"""

import random

from rag_system.learning import ChunkWeights, SimulatedUser
from rag_system.messages import Classification
from rag_system.offline_model import offline_model
from rag_system.orchestrator import Orchestrator
from tests.evals.gold_set import QUESTIONS

ROUNDS = 3


async def measure(orchestrator, questions, field="question") -> tuple[int, int]:
    """(expected documents found among the sources, off-target sources)."""
    found = off_target = 0
    for question in questions:
        answer = await orchestrator.answer(
            question[field], Classification(question.get("clearance", "internal"))
        )
        expected = set(question["expected_documents"])
        found += len(expected & {source.doc_id for source in answer.sources})
        off_target += sum(source.doc_id not in expected for source in answer.sources)
    return found, off_target


async def give_feedback(orchestrator, weights, questions) -> None:
    user = SimulatedUser(random.Random(42), wrong_share=0.1)
    for _ in range(ROUNDS):
        for question in questions:
            answer = await orchestrator.answer(
                question["question"],
                Classification(question.get("clearance", "internal")),
            )
            ratings = user.rate(answer, set(question["expected_documents"]))
            weights.apply(question["question"], ratings)


def learner(store, embedder) -> tuple[Orchestrator, ChunkWeights]:
    """An orchestrator that learns; ratings compare questions with the same
    embedder that built the index."""
    weights = ChunkWeights(embedder)
    return Orchestrator(store, offline_model(), weights=weights), weights


async def test_feedback_cuts_off_target_sources_without_losing_expected_ones(
    corpus_store, local_embedder
):
    orchestrator, weights = learner(corpus_store, local_embedder)
    same_before = await measure(orchestrator, QUESTIONS)
    paraphrases_before = await measure(orchestrator, QUESTIONS, "paraphrase")

    await give_feedback(orchestrator, weights, QUESTIONS)

    same_after = await measure(orchestrator, QUESTIONS)
    paraphrases_after = await measure(orchestrator, QUESTIONS, "paraphrase")
    assert (same_before, same_after) == ((29, 145), (29, 33))
    assert (paraphrases_before, paraphrases_after) == ((28, 209), (28, 155))


async def test_feedback_leaves_questions_it_was_not_given_for_unchanged(
    corpus_store, local_embedder
):
    rated, not_rated = QUESTIONS[0::2], QUESTIONS[1::2]
    orchestrator, weights = learner(corpus_store, local_embedder)
    before = await measure(orchestrator, not_rated)

    await give_feedback(orchestrator, weights, rated)

    assert (before, await measure(orchestrator, not_rated)) == ((14, 38), (14, 38))
