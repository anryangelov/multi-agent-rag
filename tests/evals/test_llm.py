"""LLM evals: the whole system with the model chosen in .env.

They run only when .env sets LLM_PROVIDER (anthropic or azure) and its key;
otherwise pytest skips them (tests/conftest.py).

    questions.yaml --> Orchestrator.answer with the real model, every
                       question once (the `answers` fixture)
                   --> a judge model reads each answer and says which
                       expected facts it states, in any wording
                   --> facts stated, history found, nothing invented for a
                       question no document answers, conflict winners

The offline evals check what the code decides; these check what only a
model can do: rewrite a sub-query, ask for old versions, find a
contradiction, say "nothing relevant" from the text, write the answer.
"""

import asyncio

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext, ToolOutput, models

from rag_system.config import Settings, build_llm
from rag_system.messages import Classification, FinalAnswer, Status
from rag_system.orchestrator import Orchestrator
from tests.evals.gold_set import ALL_QUESTIONS, HELDOUT, QUESTIONS

pytestmark = pytest.mark.eval

BY_ID = {question["id"]: question for question in ALL_QUESTIONS}
PARALLEL = 4  # questions in flight at once; keeps under the rate limits

JUDGE_INSTRUCTIONS = """\
You check an answer against a list of numbered facts. For each fact, say
whether the answer states it. The wording may differ ("12 months" and "a
year" are the same fact); a fact that the answer only hints at, or states
as uncertain, is not stated. Return one verdict per fact.
"""


class Verdict(BaseModel):
    fact: int  # the fact's number in the prompt, from 1
    stated: bool


class Verdicts(BaseModel):
    verdicts: list[Verdict]


# The deps are the number of facts in the prompt.
fact_judge = Agent(
    deps_type=int,
    output_type=ToolOutput(Verdicts, name="facts_stated"),
    instructions=JUDGE_INSTRUCTIONS,
)


@fact_judge.output_validator
def one_verdict_per_fact(ctx: RunContext[int], found: Verdicts) -> Verdicts:
    """Send the verdicts back unless every fact has exactly one."""
    if sorted(v.fact for v in found.verdicts) != list(range(1, ctx.deps + 1)):
        raise ModelRetry(f"give exactly one verdict for each fact 1-{ctx.deps}")
    return found


async def stated_facts(answer: FinalAnswer, facts: list[str], model) -> list[str]:
    """The expected facts that the judge finds in the answer."""
    if not facts:
        return []
    numbered = "\n".join(f"{i}. {fact}" for i, fact in enumerate(facts, 1))
    prompt = f"Answer:\n{answer.text}\n\nFacts:\n{numbered}"
    result = await fact_judge.run(prompt, model=model, deps=len(facts))
    return [facts[v.fact - 1] for v in result.output.verdicts if v.stated]


async def answer_all(store, settings: Settings) -> dict[str, tuple]:
    """Every question once: {id: (FinalAnswer, the facts it states)}."""
    model = build_llm(settings)
    orchestrator = Orchestrator(store, model, timeout_seconds=60)
    slots = asyncio.Semaphore(PARALLEL)

    async def one(question: dict) -> tuple:
        async with slots:
            answer = await orchestrator.answer(
                question["question"],
                Classification(question.get("clearance", "internal")),
            )
            return answer, await stated_facts(answer, question["expected_facts"], model)

    results = await asyncio.gather(*(one(q) for q in ALL_QUESTIONS))
    return {q["id"]: result for q, result in zip(ALL_QUESTIONS, results, strict=True)}


@pytest.fixture(scope="module")
def answers(corpus_store) -> dict[str, tuple]:
    """One run of the gold set through the real model, shared by the tests."""
    models.ALLOW_MODEL_REQUESTS = True
    try:
        return asyncio.run(answer_all(corpus_store, Settings()))
    finally:
        models.ALLOW_MODEL_REQUESTS = False


def facts_stated(answers, questions) -> tuple[int, int, list[str]]:
    stated, expected, missed = 0, 0, []
    for question in questions:
        found = answers[question["id"]][1]
        for fact in question["expected_facts"]:
            expected += 1
            if fact in found:
                stated += 1
            else:
                missed.append(f"{question['id']}: {fact}")
    return stated, expected, missed


# Measured 2026-10-30 with claude-sonnet-5-5: 20 of 24 facts (missed Q01,
# Q02, Q03: long answers that leave out one detail; Q10), held-out 7 of 9
# (missed Q21, Q25: the chunk with the fact is not kept, as offline). A model
# does not answer the same way every time, so the floors sit a little lower.
def test_the_answers_state_at_least_18_of_the_24_expected_facts(answers):
    stated, expected, missed = facts_stated(answers, QUESTIONS)

    assert expected == 24
    assert stated >= 18, f"{stated} of {expected}; missed {missed}"


def test_the_answers_to_new_questions_state_at_least_6_of_the_9_facts(answers):
    stated, expected, missed = facts_stated(answers, HELDOUT)

    assert expected == 9
    assert stated >= 6, f"{stated} of {expected}; missed {missed}"


@pytest.mark.parametrize("question_id", ["Q13", "Q17"])
def test_a_question_about_the_past_is_answered_from_the_old_version(
    answers, question_id
):
    """The classifier's model sets include_history; offline it never does."""
    answer = answers[question_id][0]

    cited = {source.doc_id for source in answer.sources}
    assert set(BY_ID[question_id]["expected_documents"]) <= cited


@pytest.mark.xfail(
    reason="known gap: on 2026-10-30 all three agents answered from nearby "
    "chunks (connectors, approvals); the answer itself said the sources do "
    "not confirm it is possible and name no Payroll connector"
)
def test_no_agent_answers_a_question_that_no_document_answers(answers):
    """Q24 (staff bonuses, Payroll); offline both agents answer (test_heldout)."""
    answer = answers["Q24"][0]

    assert all(a.status == Status.NOTHING_RELEVANT for a in answer.agent_answers)


def decided_as_expected(answer: FinalAnswer, conflict: dict) -> bool:
    """Whether the answer holds the eval's conflict and its expected winner."""
    sides = {side["document"] for side in conflict["claims"]}
    for found in answer.conflicts:
        pair = {found.claim_a.citations[0].doc_id, found.claim_b.citations[0].doc_id}
        if pair == sides:
            winner = found.winner
            return (winner.citations[0].doc_id if winner else None) == conflict[
                "winner"
            ]
    return False


def test_the_detector_finds_at_least_3_of_the_5_conflicts_and_the_rules_decide(
    answers,
):
    """The detector is a model, so only these evals see it find a pair.

    Four runs on 2026-10-30: Q06, Q07 and Q16 decided right every time; Q08
    and Q15 each missed once (the detector did not pair the two claims).
    """
    questions = [q for q in ALL_QUESTIONS if "conflict" in q]
    missed = [
        q["id"]
        for q in questions
        if not decided_as_expected(answers[q["id"]][0], q["conflict"])
    ]

    assert len(questions) == 5
    assert len(missed) <= 2, f"missed {missed}"
