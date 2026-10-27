"""The agent communication protocol rejects messages that make no sense."""

from datetime import date

import pytest
from pydantic import ValidationError

from rag_system.messages import (
    AgentAnswer,
    AgentTask,
    Citation,
    Claim,
    Classification,
    Domain,
    Kind,
    Plan,
    Status,
    SubQuery,
)


def citation(doc_id: str = "CMP-4") -> Citation:
    return Citation(
        doc_id=doc_id,
        title="Pre-Production Compliance Checklist for Services",
        section="The checklist",
        version=1,
        effective_date=date(2025, 10, 1),
        kind=Kind.STANDARD,
    )


def claim() -> Claim:
    return Claim(text="Complete the checklist first.", citations=[citation()])


def test_a_plan_needs_at_least_one_sub_query():
    with pytest.raises(ValidationError):
        Plan(sub_queries=[])


def test_a_plan_asks_each_domain_at_most_once():
    with pytest.raises(ValidationError, match="more than once"):
        Plan(
            sub_queries=[
                SubQuery(domain=Domain.TECHNICAL, text="How do I deploy?"),
                SubQuery(domain=Domain.TECHNICAL, text="Which pipeline?"),
            ]
        )


def test_a_claim_needs_a_source():
    with pytest.raises(ValidationError):
        Claim(text="Complete the checklist first.", citations=[])


@pytest.mark.parametrize("doc_id", ["CMP-4", "TEC-12", "BUS-1"])
def test_a_citation_accepts_corpus_ids(doc_id):
    assert citation(doc_id).doc_id == doc_id


@pytest.mark.parametrize("doc_id", ["CMP4", "XYZ-1", "Checklist", "cmp-4"])
def test_a_citation_rejects_ids_that_are_not_corpus_ids(doc_id):
    with pytest.raises(ValidationError):
        citation(doc_id)


def test_an_answered_result_has_at_least_one_claim():
    with pytest.raises(ValidationError, match="at least one claim"):
        AgentAnswer(
            domain=Domain.COMPLIANCE, status=Status.ANSWERED, claims=[], confidence=0.7
        )
    answer = AgentAnswer(
        domain=Domain.COMPLIANCE,
        status=Status.ANSWERED,
        claims=[claim()],
        confidence=0.7,
    )
    assert answer.status is Status.ANSWERED


@pytest.mark.parametrize("status", [Status.NOTHING_RELEVANT, Status.FAILED])
def test_a_result_without_an_answer_carries_no_claims(status):
    with pytest.raises(ValidationError, match="no claims"):
        AgentAnswer(
            domain=Domain.BUSINESS,
            status=status,
            claims=[claim()],
            confidence=0.0,
            error="timeout" if status is Status.FAILED else None,
        )


def test_a_failed_result_says_why():
    with pytest.raises(ValidationError, match="error"):
        AgentAnswer(
            domain=Domain.BUSINESS, status=Status.FAILED, claims=[], confidence=0.0
        )
    failed = AgentAnswer(
        domain=Domain.BUSINESS,
        status=Status.FAILED,
        claims=[],
        confidence=0.0,
        error="the agent timed out after 30 s",
    )
    assert failed.error == "the agent timed out after 30 s"


def test_only_a_failed_result_has_an_error():
    with pytest.raises(ValidationError, match="error"):
        AgentAnswer(
            domain=Domain.BUSINESS,
            status=Status.ANSWERED,
            claims=[claim()],
            confidence=0.7,
            error="something",
        )


@pytest.mark.parametrize("confidence", [-0.1, 1.2])
def test_confidence_is_between_zero_and_one(confidence):
    with pytest.raises(ValidationError):
        AgentAnswer(
            domain=Domain.COMPLIANCE,
            status=Status.ANSWERED,
            claims=[claim()],
            confidence=confidence,
        )


def test_an_agent_cannot_change_the_task_it_received():
    task = AgentTask(
        question="What compliance checks are needed?",
        sub_query=SubQuery(
            domain=Domain.COMPLIANCE, text="What checks before going live?"
        ),
        clearance=Classification.INTERNAL,
    )
    with pytest.raises(ValidationError):
        task.clearance = Classification.CONFIDENTIAL


def test_an_agent_cannot_change_a_claim_after_returning_it():
    returned = claim()
    with pytest.raises(ValidationError):
        returned.text = "Something else."


@pytest.mark.parametrize(
    ("clearance", "document", "allowed"),
    [
        (Classification.INTERNAL, Classification.PUBLIC, True),
        (Classification.INTERNAL, Classification.INTERNAL, True),
        (Classification.INTERNAL, Classification.CONFIDENTIAL, False),
        (Classification.PUBLIC, Classification.INTERNAL, False),
        (Classification.CONFIDENTIAL, Classification.CONFIDENTIAL, True),
    ],
)
def test_a_clearance_allows_documents_up_to_its_own_level(clearance, document, allowed):
    assert clearance.allows(document) is allowed


def test_each_domain_has_the_prefix_of_its_document_ids():
    assert {d: d.prefix for d in Domain} == {
        Domain.TECHNICAL: "TEC",
        Domain.BUSINESS: "BUS",
        Domain.COMPLIANCE: "CMP",
    }
