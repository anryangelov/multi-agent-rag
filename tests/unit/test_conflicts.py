"""Two claims that contradict each other: which one wins, and why."""

import re
from datetime import date

from pydantic_ai.messages import ModelResponse, ToolCallPart

from rag_system.conflicts import ConflictChecker
from rag_system.ingestion import Document, chunk_document
from rag_system.messages import Claim, Classification, Decision, Domain, Kind
from rag_system.offline_model import offline_model
from rag_system.vector_store import InMemoryVectorStore
from tests.fakes import WordHashEmbedder, offline_except


def document(
    doc_id: str,
    body: str,
    kind: Kind,
    owner: str = "Platform Engineering",
    classification: Classification = Classification.INTERNAL,
) -> Document:
    domain = {"TEC": Domain.TECHNICAL, "BUS": Domain.BUSINESS, "CMP": Domain.COMPLIANCE}
    return Document(
        id=doc_id,
        title=f"Document {doc_id}",
        domain=domain[doc_id[:3]],
        kind=kind,
        version=1,
        effective_date=date(2026, 1, 1),
        classification=classification,
        owner=owner,
        body=body,
    )


def store_with(*documents: Document) -> InMemoryVectorStore:
    store = InMemoryVectorStore(WordHashEmbedder())
    for each in documents:
        store.add(chunk_document(each))
    return store


def claim(text: str, source: Document) -> Claim:
    """A claim as an agent returns it: its text and the chunk it comes from."""
    return Claim(text=text, citations=[chunk_document(source)[0].citation()])


def detector_finding(first: int, second: int, topic: str):
    """Stands in for the detector model: it reports one contradicting pair."""

    def detect(messages, info):
        pair = {"claim_a": first, "claim_b": second, "topic": topic}
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"pairs": [pair]})]
        )

    return detect


def judge_must_not_run(messages, info):
    raise AssertionError("the judge was asked although the kinds differ")


RUNBOOK = document(
    "TEC-4", "## Debug logging\n\nDebug logs are kept for 30 days.", Kind.RUNBOOK
)
POLICY = document(
    "CMP-3",
    "## Retention\n\nAPI request logs, including debug logs, are kept for 90 days.",
    Kind.POLICY,
    owner="Compliance",
)


async def test_between_two_kinds_the_stronger_kind_wins_without_asking_the_judge():
    claims = [
        claim("Debug logs are kept for 30 days.", RUNBOOK),
        claim("API request logs, including debug logs, are kept for 90 days.", POLICY),
    ]
    checker = ConflictChecker(
        store_with(RUNBOOK, POLICY),
        offline_except(
            conflicts=detector_finding(1, 2, "debug log retention"),
            evidence=judge_must_not_run,
        ),
    )

    [conflict] = await checker.check(claims, Classification.INTERNAL)

    assert conflict.topic == "debug log retention"
    assert conflict.decision is Decision.KIND
    assert conflict.winner == claims[1]
    assert (conflict.score_a, conflict.score_b) == (1, 4)
    assert conflict.reason == "CMP-3 (policy) overrules TEC-4 (runbook)"


async def test_offline_no_conflict_is_found():
    claims = [
        claim("Debug logs are kept for 30 days.", RUNBOOK),
        claim("API request logs, including debug logs, are kept for 90 days.", POLICY),
    ]
    checker = ConflictChecker(store_with(RUNBOOK, POLICY), offline_model())

    assert await checker.check(claims, Classification.INTERNAL) == []


def judge_labelling(supports: dict[str, str], shown: list[str]):
    """Stands in for the judge model: labels the passages it was shown whose
    text holds a given phrase; records which passages it saw."""

    def label(messages, info):
        prompt = messages[-1].parts[-1].content
        found = re.findall(r'<chunk id="([^"]+)">\n(.*?)\n</chunk>', prompt, re.S)
        labels = []
        for chunk_id, text in found:
            shown.append(chunk_id)
            side = next(
                (s for phrase, s in supports.items() if phrase in text), "neither"
            )
            labels.append({"chunk_id": chunk_id, "supports": side})
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"labels": labels})]
        )

    return label


HANDBOOK = document(
    "BUS-4",
    "## After go-live\n\n"
    "A rollback of a workflow needs the approval of your team lead.",
    Kind.GUIDE,
    owner="Process Excellence Office",
)
CHANGES = document(
    "BUS-7",
    "## Rolling back\n\n"
    "A rollback of a workflow is not a change and needs no approval.",
    Kind.GUIDE,
    owner="Process Excellence Office",
)
RELEASES = document(
    "TEC-3",
    "## Rollback\n\nA workflow rollback is done in the console as described in "
    "Changing a Running Automation (BUS-7).",
    Kind.STANDARD,
)
ROLLBACK_CLAIMS = [
    claim("A rollback of a workflow needs the approval of your team lead.", HANDBOOK),
    claim("A rollback of a workflow is not a change and needs no approval.", CHANGES),
]


async def test_between_two_guides_the_side_other_documents_support_wins():
    shown = []
    checker = ConflictChecker(
        store_with(HANDBOOK, CHANGES, RELEASES),
        offline_except(
            conflicts=detector_finding(1, 2, "rollback approval"),
            evidence=judge_labelling({"(BUS-7)": "b"}, shown),
        ),
    )

    [conflict] = await checker.check(ROLLBACK_CLAIMS, Classification.INTERNAL)

    assert conflict.decision is Decision.EVIDENCE
    assert conflict.winner == ROLLBACK_CLAIMS[1]
    assert (conflict.score_a, conflict.score_b) == (0, 1)
    assert conflict.reason == (
        "1 other document supports BUS-7 (TEC-3); no other document supports BUS-4"
    )
    assert [citation.doc_id for citation in conflict.evidence] == ["TEC-3"]
    # The two disputing documents never testify for themselves.
    assert shown and all(chunk_id.startswith("TEC-3") for chunk_id in shown)


async def test_when_no_other_document_takes_a_side_there_is_no_winner():
    checker = ConflictChecker(
        store_with(HANDBOOK, CHANGES, RELEASES),
        offline_except(conflicts=detector_finding(1, 2, "rollback approval")),
    )

    [conflict] = await checker.check(ROLLBACK_CLAIMS, Classification.INTERNAL)

    assert conflict.decision is Decision.NO_WINNER
    assert conflict.winner is None
    assert conflict.reason == (
        "BUS-4 and BUS-7 are both guides and no other document supports each; "
        "ask the owners: Process Excellence Office; Process Excellence Office"
    )


async def test_a_document_above_the_callers_clearance_is_never_evidence():
    incident = document(
        "CMP-8",
        "## Findings\n\nA rollback of a workflow needs no approval (BUS-7).",
        Kind.REPORT,
        classification=Classification.CONFIDENTIAL,
    )
    shown = []
    checker = ConflictChecker(
        store_with(HANDBOOK, CHANGES, incident),
        offline_except(
            conflicts=detector_finding(1, 2, "rollback approval"),
            evidence=judge_labelling({"(BUS-7)": "b"}, shown),
        ),
    )

    [conflict] = await checker.check(ROLLBACK_CLAIMS, Classification.INTERNAL)

    assert not any(chunk_id.startswith("CMP-8") for chunk_id in shown)
    assert conflict.decision is Decision.NO_WINNER


async def test_a_pair_naming_a_claim_that_does_not_exist_is_sent_back():
    calls = []

    def detector_wrong_once(messages, info):
        calls.append(messages)
        first = 7 if len(calls) == 1 else 1
        return detector_finding(first, 2, "debug log retention")(messages, info)

    claims = [
        claim("Debug logs are kept for 30 days.", RUNBOOK),
        claim("API request logs, including debug logs, are kept for 90 days.", POLICY),
    ]
    checker = ConflictChecker(
        store_with(RUNBOOK, POLICY), offline_except(conflicts=detector_wrong_once)
    )

    [conflict] = await checker.check(claims, Classification.INTERNAL)

    assert len(calls) == 2
    assert conflict.winner == claims[1]
