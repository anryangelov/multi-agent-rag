"""Monitoring records every question and sums up how the agents perform."""

from datetime import date

import pytest

from rag_system.learning import Rating
from rag_system.messages import (
    AgentAnswer,
    Citation,
    Claim,
    Domain,
    FinalAnswer,
    Kind,
    Plan,
    Status,
    SubQuery,
)
from rag_system.monitoring import Monitor, Outcome


def citation(chunk_id: str) -> Citation:
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


def answered(domain: Domain, chunk_id: str) -> AgentAnswer:
    claim = Claim(text="A claim.", citations=[citation(chunk_id)])
    return AgentAnswer(
        domain=domain,
        status=Status.ANSWERED,
        claims=[claim],
        best_similarity=0.5,
        chunks_read=["TEC-1#1", "TEC-1#2", "TEC-1#3"],
    )


def failed(domain: Domain) -> AgentAnswer:
    return AgentAnswer(
        domain=domain, status=Status.FAILED, claims=[], error="timed out after 30 s"
    )


def final(*agent_answers: AgentAnswer, cited: bool = True) -> FinalAnswer:
    sources = [c for a in agent_answers for claim in a.claims for c in claim.citations]
    return FinalAnswer(
        question="How do I deploy a new service?",
        plan=Plan(
            sub_queries=[SubQuery(domain=a.domain, text="?") for a in agent_answers]
        ),
        agent_answers=list(agent_answers),
        text="...",
        sources=sources if cited else [],
    )


def record(monitor: Monitor, answer: FinalAnswer, seconds: float = 1.0) -> None:
    agent_seconds = {a.domain: seconds / 2 for a in answer.agent_answers}
    monitor.record(answer, seconds, agent_seconds, "minishlab/potion-base-8M")


@pytest.mark.parametrize(
    ("answer", "outcome"),
    [
        (final(answered(Domain.TECHNICAL, "TEC-1#1")), Outcome.SUCCESSFUL),
        (
            final(answered(Domain.TECHNICAL, "TEC-1#1"), failed(Domain.COMPLIANCE)),
            Outcome.PARTIAL,
        ),
        (final(failed(Domain.TECHNICAL), cited=False), Outcome.FAILED),
    ],
)
def test_a_question_is_successful_partial_or_failed(answer, outcome):
    monitor = Monitor()

    record(monitor, answer)

    [entry] = monitor.records
    assert entry.outcome is outcome
    assert entry.embedding_model == "minishlab/potion-base-8M"


def test_an_answer_with_a_warning_is_partial():
    monitor = Monitor()
    answer = final(answered(Domain.TECHNICAL, "TEC-1#1")).model_copy(
        update={"warnings": ["conflicts not checked (TimeoutError: )"]}
    )

    record(monitor, answer)

    assert monitor.records[0].outcome is Outcome.PARTIAL


def test_the_summary_gives_the_success_rate_and_each_agents_statuses_and_time():
    monitor = Monitor()
    record(monitor, final(answered(Domain.TECHNICAL, "TEC-1#1")), seconds=2.0)
    record(
        monitor,
        final(answered(Domain.TECHNICAL, "TEC-1#1"), failed(Domain.COMPLIANCE)),
        seconds=4.0,
    )

    summary = monitor.summary()

    assert summary.questions == 2
    assert summary.success_rate == 0.5
    technical, compliance = summary.agents
    assert technical.domain is Domain.TECHNICAL
    assert technical.asked == 2
    assert technical.answered == 1.0
    assert technical.mean_seconds == 1.5
    assert compliance.failed == 1.0


def test_the_summary_gives_the_share_of_each_agents_sources_rated_useful():
    monitor = Monitor()
    record(monitor, final(answered(Domain.TECHNICAL, "TEC-1#1")))

    monitor.record_ratings(
        [
            Rating(chunk_id="TEC-1#1", useful=True),
            Rating(chunk_id="TEC-6#5", useful=False),
            Rating(chunk_id="TEC-1#2", useful=True),
            Rating(chunk_id="TEC-3#1", useful=True),
        ]
    )

    [technical] = monitor.summary().agents
    assert technical.rated_useful == 0.75


def test_the_report_is_a_plain_text_table():
    monitor = Monitor()
    record(monitor, final(answered(Domain.TECHNICAL, "TEC-1#1")))

    report = monitor.report()

    assert "questions: 1, successful: 100%" in report
    assert "technical" in report
