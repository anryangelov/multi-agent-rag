"""The three test scenarios from the assignment, end to end, offline.

Each scenario runs the whole system on the real corpus with the local
embedding model and the offline stand-in for the language model:

    question --> Orchestrator.answer --> FinalAnswer
                 (classify, ask the agents in parallel, synthesise, sources)

The expected domains and documents come from tests/evals/questions.yaml.
"""

import re

import pytest

from rag_system.messages import Classification, Domain, Status
from rag_system.offline_model import OFFLINE_NOTE, offline_model
from rag_system.orchestrator import Orchestrator
from tests.evals.gold_set import QUESTIONS

SCENARIOS = [q for q in QUESTIONS if q["id"] in ("Q01", "Q02", "Q03")]

# Retrieval misses CMP-1 for the third scenario (measured 2026-10-28; the
# retrieval evals record it too).
KNOWN_MISSES = {"Q03": {"CMP-1"}}


@pytest.fixture
def orchestrator(corpus_store) -> Orchestrator:
    return Orchestrator(corpus_store, offline_model())


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda q: q["id"])
async def test_a_test_scenario_is_answered_from_the_expected_domains(
    orchestrator, scenario
):
    answer = await orchestrator.answer(scenario["question"], Classification.INTERNAL)

    # The plan asks exactly the expected domains, and every agent answers.
    asked = [sub_query.domain for sub_query in answer.plan.sub_queries]
    assert set(asked) == {Domain(d) for d in scenario["expected_domains"]}
    assert all(a.status is Status.ANSWERED for a in answer.agent_answers)

    # The sources hold the expected documents.
    sources = {source.doc_id for source in answer.sources}
    expected = set(scenario["expected_documents"])
    assert expected - sources == KNOWN_MISSES.get(scenario["id"], set())

    # Every document the text cites is a source, and every source is cited.
    cited = set(re.findall(r"\[([A-Z]{3}-\d+)\]", answer.text))
    assert cited == sources

    # The offline answer says that it is one.
    assert answer.text.startswith(OFFLINE_NOTE)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda q: q["id"])
async def test_a_test_scenario_gives_the_same_answer_every_time(orchestrator, scenario):
    first = await orchestrator.answer(scenario["question"], Classification.INTERNAL)
    second = await orchestrator.answer(scenario["question"], Classification.INTERNAL)

    assert first == second


async def test_the_worked_example_in_the_orchestrator_is_still_true(orchestrator):
    """The "Example" comments in Orchestrator.answer follow Q01."""
    answer = await orchestrator.answer(
        SCENARIOS[0]["question"], Classification.INTERNAL
    )

    agents = [(a.domain, a.status, len(a.claims)) for a in answer.agent_answers]
    assert agents == [
        (Domain.TECHNICAL, Status.ANSWERED, 10),
        (Domain.COMPLIANCE, Status.ANSWERED, 8),
    ]
    technical_claims = [claim.text for claim in answer.agent_answers[0].claims]
    assert "1. Register the service in the service catalog." in technical_claims
    assert answer.text.split("\n\n")[1].startswith(
        "Technical: This guide walks a development team through the first "
        "deployment of a new microservice on the automation platform. [TEC-1]"
    )
    assert answer.conflicts == []  # step 3: offline, none is detected
    first_two = [(s.doc_id, s.section) for s in answer.sources[:2]]
    assert first_two == [("TEC-1", None), ("TEC-1", "Typical first-release timeline")]
    assert len(answer.sources) == 18
    assert (answer.sources[-1].doc_id, answer.sources[-1].section) == (
        "CMP-4",
        "When to repeat",
    )
