"""A domain agent answers its sub-question from its own domain's documents."""

import asyncio
from datetime import date

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from rag_system.domain_agents import DomainAgent
from rag_system.ingestion import Document, chunk_document
from rag_system.messages import (
    AgentTask,
    Classification,
    Domain,
    Kind,
    Status,
    SubQuery,
)
from rag_system.offline_model import offline_model
from rag_system.vector_store import InMemoryVectorStore
from tests.fakes import WordHashEmbedder


def document(doc_id: str, body: str, domain: Domain = Domain.TECHNICAL) -> Document:
    return Document(
        id=doc_id,
        title=f"Document {doc_id}",
        domain=domain,
        kind=Kind.STANDARD,
        version=2,
        effective_date=date(2026, 1, 1),
        status="current",
        classification=Classification.INTERNAL,
        owner="Platform Engineering",
        body=body,
    )


def store_with(*documents: Document) -> InMemoryVectorStore:
    store = InMemoryVectorStore(WordHashEmbedder())
    for each in documents:
        store.add(chunk_document(each))
    return store


def task(question: str, domain: Domain = Domain.TECHNICAL) -> AgentTask:
    return AgentTask(
        question=question,
        sub_query=SubQuery(domain=domain, text=question),
        clearance=Classification.INTERNAL,
    )


async def test_the_agent_answers_with_a_claim_that_cites_the_chunk_it_found():
    store = store_with(
        document(
            "TEC-3",
            "## Approvals\n\nA production release needs two approvers. "
            "One of them is from another team.",
        )
    )
    agent = DomainAgent(Domain.TECHNICAL, store, offline_model())

    answer = await agent.answer(
        task("How many approvers does a production release need?")
    )

    assert answer.status is Status.ANSWERED
    [claim] = answer.claims
    assert claim.text == "A production release needs two approvers."
    [citation] = claim.citations
    assert citation.doc_id == "TEC-3"
    assert citation.section == "Approvals"
    assert citation.version == 2
    assert citation.kind is Kind.STANDARD


async def test_the_agent_keeps_at_least_3_chunks_and_drops_the_rest_below_0_4():
    related = [
        document("TEC-1", "Rollback a failed deployment with the release pipeline."),
        document("TEC-2", "A failed deployment is rolled back by the pipeline."),
    ]
    unrelated = [
        document(f"TEC-{n}", text)
        for n, text in [
            (3, "Quarterly invoices list every vendor contract."),
            (4, "Office plants are watered on Fridays."),
            (5, "The canteen menu changes every week."),
            (6, "Parking badges expire after twelve months."),
        ]
    ]
    agent = DomainAgent(
        Domain.TECHNICAL, store_with(*related, *unrelated), offline_model()
    )

    answer = await agent.answer(task("How do I rollback a failed deployment?"))

    cited = [claim.citations[0].doc_id for claim in answer.claims]
    assert len(cited) == 3
    assert {"TEC-1", "TEC-2"} <= set(cited)


async def test_the_agent_keeps_at_most_10_chunks():
    documents = [
        document(f"TEC-{n}", f"Deployment rule {n}: every deployment needs a ticket.")
        for n in range(1, 15)
    ]
    agent = DomainAgent(Domain.TECHNICAL, store_with(*documents), offline_model())

    answer = await agent.answer(task("Does every deployment need a ticket?"))

    assert len(answer.claims) == 10


async def test_when_even_the_best_chunk_is_below_0_4_the_agent_has_nothing_relevant():
    store = store_with(document("TEC-4", "Office plants are watered on Fridays."))
    agent = DomainAgent(Domain.TECHNICAL, store, offline_model())

    answer = await agent.answer(task("How do I rollback a failed deployment?"))

    assert answer.status is Status.NOTHING_RELEVANT
    assert answer.claims == []


async def test_a_domain_with_no_readable_chunks_has_nothing_relevant():
    store = store_with(
        document("BUS-1", "A deployment needs a ticket.", Domain.BUSINESS)
    )
    agent = DomainAgent(Domain.TECHNICAL, store, offline_model())

    answer = await agent.answer(task("Does a deployment need a ticket?"))

    assert answer.status is Status.NOTHING_RELEVANT


async def test_a_citation_of_a_chunk_the_model_was_not_given_is_sent_back_to_fix():
    store = store_with(document("TEC-3", "A production release needs two approvers."))
    calls = []

    def model_that_invents_a_source_once(messages, info):
        """Stands in for a real model: first cites a made-up chunk, then a real one."""
        calls.append(messages)
        chunk_id = "TEC-99#1" if len(calls) == 1 else "TEC-3#1"
        claim = {"text": "Two approvers are needed.", "chunk_ids": [chunk_id]}
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"claims": [claim]})]
        )

    agent = DomainAgent(
        Domain.TECHNICAL, store, FunctionModel(model_that_invents_a_source_once)
    )

    answer = await agent.answer(task("How many approvers does a release need?"))

    assert len(calls) == 2
    assert answer.claims[0].citations[0].doc_id == "TEC-3"


def answering_with(claims: list[dict]):
    """Stands in for a real model that returns these claims."""

    def model(messages, info):
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"claims": claims})]
        )

    return FunctionModel(model)


RELEASE_DOC = document("TEC-3", "A production release needs two approvers.")


async def test_a_model_that_finds_no_answer_in_the_chunks_gives_nothing_relevant():
    agent = DomainAgent(Domain.TECHNICAL, store_with(RELEASE_DOC), answering_with([]))

    answer = await agent.answer(task("How many approvers does a release need?"))

    assert answer.status is Status.NOTHING_RELEVANT


async def test_a_model_error_becomes_a_failed_answer_with_the_error():
    def broken_model(messages, info):
        raise ConnectionError("Azure OpenAI is unreachable")

    agent = DomainAgent(
        Domain.TECHNICAL, store_with(RELEASE_DOC), FunctionModel(broken_model)
    )

    answer = await agent.answer(task("How many approvers does a release need?"))

    assert answer.status is Status.FAILED
    assert "Azure OpenAI is unreachable" in answer.error


async def test_a_model_slower_than_the_timeout_becomes_a_failed_answer():
    async def slow_model(messages, info):
        await asyncio.sleep(1)

    agent = DomainAgent(
        Domain.TECHNICAL,
        store_with(RELEASE_DOC),
        FunctionModel(slow_model),
        timeout_seconds=0.01,
    )

    answer = await agent.answer(task("How many approvers does a release need?"))

    assert answer.status is Status.FAILED
    assert "timed out after 0.01 s" in answer.error


async def test_the_agent_never_cites_a_document_above_the_callers_clearance():
    secret = document(
        "TEC-8", "A production release of the vault needs three approvers."
    )
    secret = secret.model_copy(update={"classification": Classification.CONFIDENTIAL})
    store = store_with(RELEASE_DOC, secret)
    agent = DomainAgent(Domain.TECHNICAL, store, offline_model())

    answer = await agent.answer(
        task("How many approvers does a production release need?")
    )

    cited = {c.doc_id for claim in answer.claims for c in claim.citations}
    assert cited == {"TEC-3"}


async def test_an_offline_claim_from_a_numbered_list_keeps_the_first_item_whole():
    store = store_with(
        document(
            "TEC-1",
            "## Going to production\n\n"
            "1. Complete the compliance checklist before the release.\n"
            "2. Ask two approvers.",
        )
    )
    agent = DomainAgent(Domain.TECHNICAL, store, offline_model())

    answer = await agent.answer(
        task("Which compliance checklist comes before the release to production?")
    )

    assert answer.claims[0].text == (
        "1. Complete the compliance checklist before the release."
    )
