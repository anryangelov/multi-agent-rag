"""The orchestrator turns a question into one answer with checked citations."""

import re
from datetime import date

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from rag_system.ingestion import Document, chunk_document
from rag_system.messages import Classification, Domain, Kind, Status
from rag_system.offline_model import offline_model
from rag_system.orchestrator import NOTHING_FOUND, Orchestrator
from rag_system.vector_store import InMemoryVectorStore
from tests.fakes import WordHashEmbedder


def document(doc_id: str, body: str, domain: Domain) -> Document:
    return Document(
        id=doc_id,
        title=f"Document {doc_id}",
        domain=domain,
        kind=Kind.STANDARD,
        version=1,
        effective_date=date(2026, 1, 1),
        classification=Classification.INTERNAL,
        owner="Platform Engineering",
        body=body,
    )


def store_with(*documents: Document) -> InMemoryVectorStore:
    store = InMemoryVectorStore(WordHashEmbedder())
    for each in documents:
        store.add(chunk_document(each))
    return store


RELEASE_CORPUS = [
    document(
        "TEC-3",
        "## Approvals\n\nA production release of a microservice needs two approvers.",
        Domain.TECHNICAL,
    ),
    document(
        "CMP-4",
        "## Checks\n\nA production release of a microservice needs the "
        "compliance checklist.",
        Domain.COMPLIANCE,
    ),
]
QUESTION = "What does a production release of a microservice need?"


async def test_the_answer_combines_the_domains_and_cites_their_documents():
    orchestrator = Orchestrator(store_with(*RELEASE_CORPUS), offline_model())

    answer = await orchestrator.answer(QUESTION, Classification.INTERNAL)

    assert [a.domain for a in answer.agent_answers] == [
        Domain.TECHNICAL,
        Domain.COMPLIANCE,
    ]
    assert all(a.status is Status.ANSWERED for a in answer.agent_answers)
    assert set(re.findall(r"\[([A-Z]{3}-\d+)\]", answer.text)) == {"TEC-3", "CMP-4"}
    assert [source.doc_id for source in answer.sources] == ["TEC-3", "CMP-4"]


def offline_except(**scripts):
    """Stands in for a real model: the offline templates, except the roles
    given here (by output name), which run the given function instead."""
    offline = offline_model().function

    def model(messages, info):
        name = info.output_tools[0].name if info.output_tools else "text"
        if name in scripts:
            return scripts[name](messages, info)
        return offline(messages, info)

    return FunctionModel(model)


async def test_an_answer_citing_a_document_no_agent_gave_is_sent_back_to_fix():
    calls = []

    def synthesis_that_invents_a_source_once(messages, info):
        calls.append(messages)
        doc_id = "TEC-99" if len(calls) == 1 else "TEC-3"
        return ModelResponse(parts=[TextPart(f"Two approvers. [{doc_id}]")])

    orchestrator = Orchestrator(
        store_with(*RELEASE_CORPUS),
        offline_except(text=synthesis_that_invents_a_source_once),
    )

    answer = await orchestrator.answer(QUESTION, Classification.INTERNAL)

    assert len(calls) == 2
    assert answer.text == "Two approvers. [TEC-3]"
    assert [source.doc_id for source in answer.sources] == ["TEC-3"]


async def test_when_one_agent_fails_the_answer_is_made_from_the_others():
    offline = offline_model().function

    def claims_failing_for_compliance(messages, info):
        if "Domain: compliance" in messages[-1].parts[-1].content:
            raise ConnectionError("Azure OpenAI is unreachable")
        return offline(messages, info)

    orchestrator = Orchestrator(
        store_with(*RELEASE_CORPUS),
        offline_except(claims=claims_failing_for_compliance),
    )

    answer = await orchestrator.answer(QUESTION, Classification.INTERNAL)

    statuses = {a.domain: a.status for a in answer.agent_answers}
    assert statuses == {
        Domain.TECHNICAL: Status.ANSWERED,
        Domain.COMPLIANCE: Status.FAILED,
    }
    assert [source.doc_id for source in answer.sources] == ["TEC-3"]


async def test_when_no_agent_has_a_claim_the_answer_says_so_without_a_model():
    def synthesis_must_not_run(messages, info):
        raise AssertionError("the synthesis was called with no claims")

    orchestrator = Orchestrator(
        store_with(*RELEASE_CORPUS),
        offline_except(text=synthesis_must_not_run),
    )

    answer = await orchestrator.answer(
        "Where are the office plants watered?", Classification.INTERNAL
    )

    assert answer.text == NOTHING_FOUND
    assert answer.sources == []
