"""The orchestrator turns a question into one answer with checked citations."""

import re
from datetime import date

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart

from rag_system.ingestion import Document, chunk_document
from rag_system.learning import ChunkWeights, Rating
from rag_system.messages import Classification, Domain, Kind, Status
from rag_system.monitoring import Monitor, Outcome
from rag_system.offline_model import offline_model
from rag_system.orchestrator import NOTHING_FOUND, Orchestrator
from rag_system.vector_store import InMemoryVectorStore
from tests.fakes import WordHashEmbedder, offline_except


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


def detector_finding_first_two(messages, info):
    """Stands in for the detector model: claims 1 and 2 contradict."""
    pair = {"claim_a": 1, "claim_b": 2, "topic": "debug log retention"}
    return ModelResponse(
        parts=[ToolCallPart(info.output_tools[0].name, {"pairs": [pair]})]
    )


RETENTION_CORPUS = [
    document(
        "TEC-4",
        "## Debug logging\n\nDebug logs are kept for 30 days.",
        Domain.TECHNICAL,
    ).model_copy(update={"kind": Kind.RUNBOOK}),
    document(
        "CMP-3",
        "## Retention\n\nDebug logs of an API are kept for 90 days.",
        Domain.COMPLIANCE,
    ).model_copy(update={"kind": Kind.POLICY}),
]


async def test_an_overruled_claim_is_named_as_overruled_not_stated_as_fact():
    orchestrator = Orchestrator(
        store_with(*RETENTION_CORPUS),
        offline_except(conflicts=detector_finding_first_two),
    )

    answer = await orchestrator.answer(
        "How long are debug logs kept?", Classification.INTERNAL
    )

    [conflict] = answer.conflicts
    assert conflict.reason == "CMP-3 (policy) overrules TEC-4 (runbook)"
    paragraphs = answer.text.split("\n\n")
    assert "Debug logs of an API are kept for 90 days. [CMP-3]" in answer.text
    assert paragraphs[-1] == (
        'Overruled: "Debug logs are kept for 30 days." [TEC-4]; '
        "CMP-3 (policy) overrules TEC-4 (runbook)."
    )
    assert not any(p.startswith("Technical:") for p in paragraphs)
    assert [source.doc_id for source in answer.sources] == ["CMP-3", "TEC-4"]


async def test_offline_the_answer_has_no_conflicts():
    orchestrator = Orchestrator(store_with(*RETENTION_CORPUS), offline_model())

    answer = await orchestrator.answer(
        "How long are debug logs kept?", Classification.INTERNAL
    )

    assert answer.conflicts == []
    assert "Debug logs are kept for 30 days. [TEC-4]" in answer.text


async def test_a_document_that_only_gave_evidence_is_cited_and_listed():
    def plan_business_only(messages, info):
        question = "Does a rollback of a workflow need an approval?"
        plan = {"sub_queries": [{"domain": "business", "text": question}]}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, plan)])

    def detector_pairing_the_two_guides(messages, info):
        prompt = messages[-1].parts[-1].content
        number = dict(re.findall(r'<claim n="(\d+)" document="([^"]+)"', prompt))
        first, second = sorted(number, key=lambda n: number[n])
        pair = {"claim_a": int(first), "claim_b": int(second), "topic": "rollback"}
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"pairs": [pair]})]
        )

    def judge_backing_bus_7(messages, info):
        prompt = messages[-1].parts[-1].content
        ids = re.findall(r'<chunk id="([^"]+)">', prompt)
        labels = [{"chunk_id": i, "supports": "b"} for i in ids if i.startswith("TEC")]
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"labels": labels})]
        )

    guides = [
        document(
            "BUS-4",
            "## Rollback\n\nA rollback of a workflow needs an approval.",
            Domain.BUSINESS,
        ).model_copy(update={"kind": Kind.GUIDE}),
        document(
            "BUS-7",
            "## Rollback\n\nA rollback of a workflow needs no approval.",
            Domain.BUSINESS,
        ).model_copy(update={"kind": Kind.GUIDE}),
        document(
            "TEC-3",
            "## Rollback\n\nA rollback of a workflow follows BUS-7.",
            Domain.TECHNICAL,
        ),
    ]
    orchestrator = Orchestrator(
        store_with(*guides),
        offline_except(
            plan=plan_business_only,
            conflicts=detector_pairing_the_two_guides,
            evidence=judge_backing_bus_7,
        ),
    )

    answer = await orchestrator.answer(
        "Does a rollback of a workflow need an approval?", Classification.INTERNAL
    )

    [conflict] = answer.conflicts
    assert conflict.winner.citations[0].doc_id == "BUS-7"
    assert answer.text.endswith("Supported by [TEC-3].")
    assert "TEC-3" in [source.doc_id for source in answer.sources]


async def test_feedback_reaches_the_agents_through_the_orchestrator():
    corpus = [
        document(f"TEC-{n}", f"Deploy a service, step {n}.", Domain.TECHNICAL)
        for n in range(1, 5)
    ]
    weights = ChunkWeights(WordHashEmbedder())
    orchestrator = Orchestrator(store_with(*corpus), offline_model(), weights=weights)
    question = "Deploy a service"
    before = await orchestrator.answer(question, Classification.INTERNAL)

    for _ in range(3):
        weights.apply(question, [Rating(chunk_id="TEC-4#1", useful=False)])
    after = await orchestrator.answer(question, Classification.INTERNAL)

    assert "TEC-4#1" in [source.chunk_id for source in before.sources]
    assert "TEC-4#1" not in [source.chunk_id for source in after.sources]


async def test_each_question_is_recorded_with_its_outcome_and_durations():
    now = [0.0]
    offline = offline_model().function

    def taking(seconds):
        """A model role that takes `seconds` on the injected clock."""

        def role(messages, info):
            now[0] += seconds
            return offline(messages, info)

        return role

    def plan_technical_only(messages, info):
        now[0] += 1.0
        plan = {"sub_queries": [{"domain": "technical", "text": QUESTION}]}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, plan)])

    monitor = Monitor()
    orchestrator = Orchestrator(
        store_with(*RELEASE_CORPUS),
        offline_except(plan=plan_technical_only, claims=taking(2.0)),
        monitor=monitor,
        clock=lambda: now[0],
    )

    await orchestrator.answer(QUESTION, Classification.INTERNAL)

    [entry] = monitor.records
    assert entry.outcome is Outcome.SUCCESSFUL
    assert entry.seconds == 3.0
    [technical] = entry.agents
    assert (technical.domain, technical.seconds) == (Domain.TECHNICAL, 2.0)
    assert technical.chunks_read == 1
    assert entry.embedding_model == "test:word-hash-64"


def failing(role: str):
    """A model role that is unreachable."""

    def role_fails(messages, info):
        raise ConnectionError(f"the {role} model is unreachable")

    return role_fails


@pytest.mark.parametrize("question", ["", "   ", "?!"])
async def test_a_question_without_a_word_is_refused_before_any_search(question):
    orchestrator = Orchestrator(
        store_with(*RELEASE_CORPUS),
        offline_except(plan=failing("plan"), claims=failing("claims")),
    )

    with pytest.raises(ValueError, match="the question is empty"):
        await orchestrator.answer(question, Classification.INTERNAL)


async def test_a_plan_with_no_domain_answers_nothing_found_without_agents():
    def plan_nothing(messages, info):
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"sub_queries": []})]
        )

    orchestrator = Orchestrator(
        store_with(*RELEASE_CORPUS),
        offline_except(plan=plan_nothing, claims=failing("claims")),
    )

    answer = await orchestrator.answer(
        "What is the weather in Sofia?", Classification.INTERNAL
    )

    assert answer.agent_answers == []
    assert answer.text == NOTHING_FOUND


async def test_when_the_classifier_fails_every_domain_is_asked():
    orchestrator = Orchestrator(
        store_with(*RELEASE_CORPUS), offline_except(plan=failing("plan"))
    )

    answer = await orchestrator.answer(QUESTION, Classification.INTERNAL)

    assert [s.domain for s in answer.plan.sub_queries] == list(Domain)
    assert all(s.text == QUESTION for s in answer.plan.sub_queries)
    assert answer.warnings == [
        "classifier failed (ConnectionError: the plan model is unreachable); "
        "every domain was asked"
    ]
    assert answer.sources


async def test_when_the_detector_fails_the_answer_says_conflicts_were_not_checked():
    orchestrator = Orchestrator(
        store_with(*RETENTION_CORPUS), offline_except(conflicts=failing("detector"))
    )

    answer = await orchestrator.answer(
        "How long are debug logs kept?", Classification.INTERNAL
    )

    assert answer.conflicts == []
    assert answer.warnings == [
        "conflicts not checked (ConnectionError: the detector model is unreachable)"
    ]
    assert "Debug logs are kept for 30 days. [TEC-4]" in answer.text


def detector_pairing_bus(messages, info):
    """Stands in for the detector model: the two BUS claims contradict."""
    prompt = messages[-1].parts[-1].content
    numbers = re.findall(r'<claim n="(\d+)" document="BUS-\d+"', prompt)
    pair = {"claim_a": int(numbers[0]), "claim_b": int(numbers[1]), "topic": "rollback"}
    return ModelResponse(
        parts=[ToolCallPart(info.output_tools[0].name, {"pairs": [pair]})]
    )


async def test_when_the_judge_fails_the_conflict_has_no_winner_and_says_why():
    guides = [
        document(
            "BUS-4",
            "## Rollback\n\nA rollback of a workflow needs an approval.",
            Domain.BUSINESS,
        ).model_copy(update={"kind": Kind.GUIDE}),
        document(
            "BUS-7",
            "## Rollback\n\nA rollback of a workflow needs no approval.",
            Domain.BUSINESS,
        ).model_copy(update={"kind": Kind.GUIDE}),
        document(
            "TEC-3",
            "## Rollback\n\nA rollback of a workflow follows BUS-7.",
            Domain.TECHNICAL,
        ),
    ]
    orchestrator = Orchestrator(
        store_with(*guides),
        offline_except(conflicts=detector_pairing_bus, evidence=failing("judge")),
    )

    answer = await orchestrator.answer(
        "Does a rollback of a workflow need an approval?", Classification.INTERNAL
    )

    [conflict] = answer.conflicts
    assert conflict.winner is None
    assert conflict.error == "ConnectionError: the judge model is unreachable"
    assert answer.warnings == [
        f"evidence not checked for the conflict on {conflict.topic} "
        "(ConnectionError: the judge model is unreachable)"
    ]


async def test_when_the_synthesis_fails_the_claims_are_listed_with_their_sources():
    orchestrator = Orchestrator(
        store_with(*RELEASE_CORPUS), offline_except(text=failing("synthesis"))
    )

    answer = await orchestrator.answer(QUESTION, Classification.INTERNAL)

    assert answer.warnings == [
        "synthesis failed (ConnectionError: the synthesis model is unreachable); "
        "the claims are listed as the agents wrote them"
    ]
    assert "[TEC-3]" in answer.text
    assert "[CMP-4]" in answer.text
    assert [source.doc_id for source in answer.sources] == ["TEC-3", "CMP-4"]
