"""Offline conflict evals: the real corpus, the real local embedding model.

    questions.yaml --> conflict: two claims an agent would write, the winner
                   --> ConflictChecker.check, the detector replaced by the
                       pair itself (finding it needs a language model)
                   --> compared with the expected winner

Between kinds (Q06, Q07, Q08) the rule decides alone. Between documents of
the same kind (Q15, Q16) the judge reads the evidence; offline these evals
check what the judge is shown, and the LLM evals check its labels.
"""

import re
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart

from rag_system.conflicts import ConflictChecker
from rag_system.ingestion import chunk_document, load_documents
from rag_system.messages import Claim, Classification, Decision
from tests.evals.gold_set import QUESTIONS
from tests.fakes import offline_except

ROOT = Path(__file__).parents[2]
CONFLICTS = {q["id"]: q["conflict"] for q in QUESTIONS if "conflict" in q}
DOCUMENTS = {document.id: document for document in load_documents(ROOT / "data")}


def claims_of(conflict: dict) -> list[Claim]:
    """The two claims, each citing its document as an agent would."""
    claims = []
    for side in conflict["claims"]:
        source = chunk_document(DOCUMENTS[side["document"]])[0]
        claims.append(Claim(text=side["text"], citations=[source.citation()]))
    return claims


def the_pair(messages, info):
    pair = {"claim_a": 1, "claim_b": 2, "topic": "the eval's conflict"}
    return ModelResponse(
        parts=[ToolCallPart(info.output_tools[0].name, {"pairs": [pair]})]
    )


def judge_recording(shown: dict[str, str], supports: dict[str, str]):
    """Records the passages the judge is shown; labels a passage for a side
    when it names that side's document in brackets, e.g. "(BUS-7)"."""

    def label(messages, info):
        prompt = messages[-1].parts[-1].content
        labels = []
        for chunk_id, text in re.findall(
            r'<chunk id="([^"]+)">\n(.*?)\n</chunk>', prompt, re.S
        ):
            shown[chunk_id] = text
            side = next((s for ref, s in supports.items() if ref in text), "neither")
            labels.append({"chunk_id": chunk_id, "supports": side})
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"labels": labels})]
        )

    return label


def judge_must_not_run(messages, info):
    raise AssertionError("the judge was asked although the kinds differ")


@pytest.mark.parametrize("question_id", ["Q06", "Q07", "Q08"])
async def test_between_kinds_the_expected_document_wins(corpus_store, question_id):
    conflict = CONFLICTS[question_id]
    checker = ConflictChecker(
        corpus_store, offline_except(conflicts=the_pair, evidence=judge_must_not_run)
    )

    [result] = await checker.check(claims_of(conflict), Classification.INTERNAL)

    assert result.decision is Decision.KIND
    assert result.winner.citations[0].doc_id == conflict["winner"]


async def test_q15_the_judge_is_shown_the_release_standard_that_backs_bus_7(
    corpus_store,
):
    """Conflict 6: TEC-3 refers the rollback of a workflow to BUS-7."""
    conflict = CONFLICTS["Q15"]
    shown = {}
    checker = ConflictChecker(
        corpus_store,
        offline_except(
            conflicts=the_pair,
            evidence=judge_recording(shown, {"(BUS-7)": "b", "(BUS-4)": "a"}),
        ),
    )

    [result] = await checker.check(claims_of(conflict), Classification.INTERNAL)

    assert "TEC-3#7" in shown
    assert not any(chunk_id.startswith(("BUS-4#", "BUS-7#")) for chunk_id in shown)
    assert result.decision is Decision.EVIDENCE
    assert result.winner.citations[0].doc_id == conflict["winner"]


async def test_q16_no_passage_the_judge_is_shown_says_who_may_read_audit_records(
    corpus_store,
):
    """Conflict 7: nothing outside BUS-6 and CMP-7 takes a side, so a careful
    judge finds no support and there is no winner (checked with a model)."""
    conflict = CONFLICTS["Q16"]
    shown = {}
    checker = ConflictChecker(
        corpus_store,
        offline_except(conflicts=the_pair, evidence=judge_recording(shown, {})),
    )

    [result] = await checker.check(claims_of(conflict), Classification.INTERNAL)

    assert shown
    for text in shown.values():
        assert not re.search(r"read access|may read|can read", text, re.I)
    assert conflict["winner"] is None
    assert result.decision is Decision.NO_WINNER
