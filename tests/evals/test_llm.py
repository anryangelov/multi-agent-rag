"""LLM evals: the whole system with the model chosen in .env.

They run only when .env sets LLM_PROVIDER (anthropic or azure) and its key;
otherwise pytest skips them (tests/conftest.py).

    questions.yaml --> Orchestrator.answer with the real model, every
                       question once (the `answers` fixture)
                   --> a judge model reads each answer and says which
                       expected facts it states, in any wording
                   --> a second judge splits the answer into statements and
                       says which the chunks the agents read support
                   --> facts that reached the model, facts stated, supported
                       statements (faithfulness), history found, nothing
                       invented for a question no document answers,
                       conflict winners

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
from tests.evals.measures import CHUNK_TEXTS, mentions

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


FAITHFULNESS_INSTRUCTIONS = """\
You check whether an answer sticks to its sources. Split the answer into
its statements of fact (skip headings, advice to ask someone, and remarks
that the sources do not say something). For each statement, say whether the
passages support it: supported means a passage says it or it follows
directly from one. A <decision> passage is the outcome of the conflict
rules, which the answer may repeat. A statement that adds a number, a name, a rule or a
condition no passage gives is not supported.
"""


class Statement(BaseModel):
    text: str
    supported: bool


class Statements(BaseModel):
    statements: list[Statement]


faithfulness_judge = Agent(
    output_type=ToolOutput(Statements, name="statements"),
    instructions=FAITHFULNESS_INSTRUCTIONS,
)


async def judged_statements(answer: FinalAnswer, model) -> list[Statement]:
    """The answer's statements, each judged against what the synthesis was
    given: the chunks the agents read and the decisions of the conflict rules."""
    read = sorted({i for a in answer.agent_answers for i in a.chunks_read})
    if not read:
        return []
    passages = "\n\n".join(
        [f"<passage>\n{CHUNK_TEXTS[i]}\n</passage>" for i in read]
        + [f"<decision>{conflict.reason}</decision>" for conflict in answer.conflicts]
    )
    prompt = f"Passages:\n{passages}\n\nAnswer:\n{answer.text}"
    result = await faithfulness_judge.run(prompt, model=model)
    return result.output.statements


async def answer_all(store, settings: Settings) -> dict[str, tuple]:
    """Every question once: {id: (FinalAnswer, the facts it states, its
    statements judged for support)}."""
    model = build_llm(settings)
    orchestrator = Orchestrator(store, model, timeout_seconds=60)
    slots = asyncio.Semaphore(PARALLEL)

    async def one(question: dict) -> tuple:
        async with slots:
            answer = await orchestrator.answer(
                question["question"],
                Classification(question.get("clearance", "internal")),
            )
            facts = await stated_facts(answer, question["expected_facts"], model)
            return answer, facts, await judged_statements(answer, model)

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


def facts_reached(answers, questions) -> tuple[int, int, list[str]]:
    """Expected facts in the chunks the agents gave the model, with the
    sub-queries the model wrote (context recall)."""
    found, expected, missed = 0, 0, []
    for question in questions:
        answer = answers[question["id"]][0]
        read = [CHUNK_TEXTS[i] for a in answer.agent_answers for i in a.chunks_read]
        for fact in question["expected_facts"]:
            expected += 1
            if any(mentions(text, fact) for text in read):
                found += 1
            else:
                missed.append(f"{question['id']}: {fact}")
    return found, expected, missed


def supported_share(answers, questions) -> tuple[int, int, list[str]]:
    """(supported statements, statements, the unsupported ones)."""
    statements = [
        (question["id"], statement)
        for question in questions
        for statement in answers[question["id"]][2]
    ]
    unsupported = [f"{qid}: {st.text}" for qid, st in statements if not st.supported]
    return len(statements) - len(unsupported), len(statements), unsupported


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


# Measured 2026-10-30 with claude-sonnet-5-5 (54 questions). A model does
# not answer the same way every time, so the floors sit a little lower.
def test_the_chunks_the_model_reads_hold_at_least_21_of_the_24_facts(answers):
    """Context recall with the sub-queries the model wrote: 22 of 24."""
    found, expected, missed = facts_reached(answers, QUESTIONS)
    print(f"facts reached, tuning: {found} of {expected}")

    assert expected == 24
    assert found >= 21, f"{found} of {expected}; missed {missed}"


def test_the_chunks_the_model_reads_hold_at_least_23_of_the_37_new_facts(answers):
    """25-26 of 37, against 24 offline: the rewritten sub-queries barely help;
    the chunk with the fact ranks too low (see test_heldout.py)."""
    found, expected, missed = facts_reached(answers, HELDOUT)
    print(f"facts reached, held-out: {found} of {expected}")

    assert expected == 37
    assert found >= 23, f"{found} of {expected}; missed {missed}"


def test_the_answers_state_at_least_18_of_the_24_expected_facts(answers):
    """20-21 of 24; misses: long answers (Q01-Q03) that leave out a detail."""
    stated, expected, missed = facts_stated(answers, QUESTIONS)
    print(f"facts stated, tuning: {stated} of {expected}")

    assert expected == 24
    assert stated >= 18, f"{stated} of {expected}; missed {missed}"


def test_the_answers_to_new_questions_state_at_least_25_of_the_37_facts(answers):
    """28 of 37."""
    stated, expected, missed = facts_stated(answers, HELDOUT)
    print(f"facts stated, held-out: {stated} of {expected}")

    assert expected == 37
    assert stated >= 25, f"{stated} of {expected}; missed {missed}"


def test_at_least_90_percent_of_the_statements_are_supported(answers):
    """Faithfulness: 97% (691 of 710). When the judge saw only the chunks it
    was 93%: about 20 of the 49 unsupported statements repeated a decision of
    the conflict rules, so the judge now sees those too. A real one, in two
    runs: Q25 invents a 90-day limit for copies of ID documents. Another run
    followed a false conflict in Q30 (BUS-2 is stricter than CMP-2, not
    opposed to it)."""
    supported, total, unsupported = supported_share(answers, ALL_QUESTIONS)
    print(f"supported: {supported} of {total}")
    for statement in unsupported:
        print("  unsupported", statement)

    assert supported >= 0.9 * total, f"{supported} of {total}"


@pytest.mark.parametrize("question_id", ["Q13", "Q17"])
def test_a_question_about_the_past_is_answered_from_the_old_version(
    answers, question_id
):
    """The classifier's model sets include_history; offline it never does."""
    answer = answers[question_id][0]

    cited = {source.doc_id for source in answer.sources}
    assert set(BY_ID[question_id]["expected_documents"]) <= cited


def test_most_questions_that_no_document_answers_end_in_nothing_relevant(answers):
    """Seven questions (payroll, meeting rooms, travel expenses, ...).

    Measured 2026-10-30: 6 of 7 (Q32, Q33, Q45, Q46, Q53, Q54); for Q24
    (staff bonuses to Payroll) the agents answered from nearby chunks
    (connectors, approvals), and the answer said the sources do not confirm
    it is possible. Offline none of the 7 ends so (test_heldout.py).
    """
    unanswerable = [q["id"] for q in ALL_QUESTIONS if not q["expected_documents"]]
    silent = [
        question_id
        for question_id in unanswerable
        if all(
            a.status == Status.NOTHING_RELEVANT
            for a in answers[question_id][0].agent_answers
        )
    ]

    assert len(unanswerable) == 7
    assert len(silent) >= 5, f"answered: {set(unanswerable) - set(silent)}"


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
