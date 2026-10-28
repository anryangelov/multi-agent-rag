"""Do the agents' claims contradict each other, and which side wins?

    orchestrator -- claims, clearance --> ConflictChecker.check(...)
        1. detect: the detector model reads every claim with its document,
           kind and date, and returns the pairs that contradict, by number
        2. score each pair:
             different kinds: each side scores its kind's rank
               (policy 4, standard 3, guide 2, runbook 1, report 0)
             same kind: each side scores the number of OTHER documents
               that support it
               a. the store is searched with each claim's text, in every
                  domain the caller may read; the two disputing documents
                  are left out of the results
               b. the judge model labels each found chunk: supports A,
                  supports B, or neither
               c. code counts the supporting documents of each side
        3. the higher score wins; equal scores: no winner
    orchestrator <-- Conflict, Conflict, ...

If the judge fails, that conflict has no winner and carries the error.

Models find and read (steps 1 and 2b); code decides (steps 2c and 3), so
every outcome has a reason that can be checked. Without a key the detector
is the offline stand-in, which finds no conflicts (offline_model.py).
"""

from enum import StrEnum

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext, ToolOutput
from pydantic_ai.models import Model

from rag_system.ingestion import Chunk
from rag_system.messages import Citation, Claim, Clearance, Conflict, Decision
from rag_system.vector_store import VectorStore

DETECTOR_INSTRUCTIONS = """\
You check the claims of a bank's automation platform assistant for
contradictions. The prompt numbers the claims and gives each one's
document, kind and date. Return every pair of claims from different
documents that cannot both be true, for example 30 days against 90 days
for the same logs, with a short topic. Claims that only differ in detail
or talk about different things are not a contradiction. Return no pair if
nothing contradicts.
"""

JUDGE_INSTRUCTIONS = """\
Two claims contradict each other. The prompt gives claim A, claim B and
passages from other documents. For each passage, say whether it supports
claim A, supports claim B, or neither. A passage supports a claim when it
states the same rule, or says that the rule is set by that claim's
document.
"""

EVIDENCE_CHUNKS = 8  # chunks searched for each side of a same-kind conflict


class Pair(BaseModel):
    claim_a: int = Field(description="The number of the first claim.")
    claim_b: int = Field(description="The number of the second claim.")
    topic: str = Field(description="What the two claims disagree about.")


class Pairs(BaseModel):
    pairs: list[Pair]


class Side(StrEnum):
    A = "a"
    B = "b"
    NEITHER = "neither"


class Label(BaseModel):
    chunk_id: str = Field(description='The id of the passage, e.g. "TEC-3#7".')
    supports: Side


class Labels(BaseModel):
    labels: list[Label]


# The model boundaries: each run gets its model from the ConflictChecker.
# The detector's deps are the claims, numbered from 1 in the prompt; the
# judge's deps are the passages it was shown, by id.
detector = Agent(
    deps_type=list[Claim],
    output_type=ToolOutput(Pairs, name="conflicts"),
    instructions=DETECTOR_INSTRUCTIONS,
)
judge = Agent(
    deps_type=dict[str, Chunk],
    output_type=ToolOutput(Labels, name="evidence"),
    instructions=JUDGE_INSTRUCTIONS,
)


@detector.output_validator
def pairs_of_given_claims(ctx: RunContext[list[Claim]], found: Pairs) -> Pairs:
    """Send the pairs back if one names a claim that does not exist."""
    count = len(ctx.deps)
    for pair in found.pairs:
        for number in (pair.claim_a, pair.claim_b):
            if not 1 <= number <= count:
                raise ModelRetry(f"claim {number} does not exist; use 1 to {count}")
        if pair.claim_a == pair.claim_b:
            raise ModelRetry(f"claim {pair.claim_a} cannot contradict itself")
    return found


@judge.output_validator
def labels_of_given_passages(
    ctx: RunContext[dict[str, Chunk]], found: Labels
) -> Labels:
    """Send the labels back if one names a passage the judge was not shown."""
    for label in found.labels:
        if label.chunk_id not in ctx.deps:
            given = ", ".join(ctx.deps)
            raise ModelRetry(f"{label.chunk_id} was not shown; label only: {given}")
    return found


class ConflictChecker:
    def __init__(self, store: VectorStore, model: Model) -> None:
        self._store = store
        self._model = model

    async def check(self, claims: list[Claim], clearance: Clearance) -> list[Conflict]:
        """Steps 1-3 of the map."""
        # 1. The detector returns the pairs that contradict.
        result = await detector.run(_numbered(claims), model=self._model, deps=claims)

        # 2-3. Score each pair; the higher score wins.
        conflicts = []
        for pair in result.output.pairs:
            a, b = claims[pair.claim_a - 1], claims[pair.claim_b - 1]
            if _source(a).kind is not _source(b).kind:
                conflicts.append(_by_kind(pair.topic, a, b))
            else:
                conflicts.append(await self._by_evidence(pair.topic, a, b, clearance))
        return conflicts

    async def _by_evidence(
        self, topic: str, a: Claim, b: Claim, clearance: Clearance
    ) -> Conflict:
        # a. The passages of other documents near either claim.
        disputing = _documents(a) | _documents(b)
        passages = {}
        for side in (a, b):
            hits = self._store.search(side.text, None, clearance, EVIDENCE_CHUNKS)
            for hit in hits:
                if hit.chunk.document.id not in disputing:
                    passages[hit.chunk.id] = hit.chunk

        # b. The judge labels each passage. If the judge fails, the conflict
        #    stays open: no evidence counted is not evidence against a side.
        labels = []
        if passages:
            try:
                result = await judge.run(
                    _judge_prompt(a, b, passages), model=self._model, deps=passages
                )
            except Exception as error:
                return _unchecked(topic, a, b, f"{type(error).__name__}: {error}")
            labels = result.output.labels

        # c. Count the supporting documents of each side.
        support = {Side.A: {}, Side.B: {}}
        for label in labels:
            if label.supports is not Side.NEITHER:
                chunk = passages[label.chunk_id]
                support[label.supports].setdefault(chunk.document.id, chunk)
        return _by_count(topic, a, b, support[Side.A], support[Side.B])


def _by_kind(topic: str, a: Claim, b: Claim) -> Conflict:
    score_a, score_b = _source(a).kind.rank, _source(b).kind.rank
    winner, loser = _source(a), _source(b)
    if score_b > score_a:
        winner, loser = loser, winner
    return Conflict(
        topic=topic,
        claim_a=a,
        claim_b=b,
        decision=Decision.KIND,
        score_a=score_a,
        score_b=score_b,
        reason=f"{winner.doc_id} ({winner.kind}) overrules "
        f"{loser.doc_id} ({loser.kind})",
    )


def _by_count(
    topic: str, a: Claim, b: Claim, for_a: dict[str, Chunk], for_b: dict[str, Chunk]
) -> Conflict:
    source_a, source_b = _source(a), _source(b)
    if len(for_a) == len(for_b):
        decision = Decision.NO_WINNER
        reason = (
            f"{source_a.doc_id} and {source_b.doc_id} are both {source_a.kind}s and "
            f"{_supports(len(for_a))} each; ask the owners: "
            f"{source_a.owner}; {source_b.owner}"
        )
    else:
        decision = Decision.EVIDENCE
        (winner, backing), (loser, other) = sorted(
            [(source_a, for_a), (source_b, for_b)], key=lambda side: -len(side[1])
        )
        reason = (
            f"{_supports(len(backing))} {winner.doc_id} ({', '.join(backing)}); "
            f"{_supports(len(other))} {loser.doc_id}"
        )
    evidence = [chunk.citation() for chunk in [*for_a.values(), *for_b.values()]]
    return Conflict(
        topic=topic,
        claim_a=a,
        claim_b=b,
        decision=decision,
        score_a=len(for_a),
        score_b=len(for_b),
        reason=reason,
        evidence=evidence,
    )


def _unchecked(topic: str, a: Claim, b: Claim, error: str) -> Conflict:
    source_a, source_b = _source(a), _source(b)
    return Conflict(
        topic=topic,
        claim_a=a,
        claim_b=b,
        decision=Decision.NO_WINNER,
        score_a=0,
        score_b=0,
        reason=(
            f"the evidence could not be checked; ask the owners: "
            f"{source_a.owner}; {source_b.owner}"
        ),
        error=error,
    )


def _supports(documents: int) -> str:
    """'no other document supports', '1 other document supports', '2 ... support'."""
    if documents == 0:
        return "no other document supports"
    if documents == 1:
        return "1 other document supports"
    return f"{documents} other documents support"


def _source(claim: Claim) -> Citation:
    """The claim's strongest source: the one its side of a conflict stands on."""
    return max(claim.citations, key=lambda citation: citation.kind.rank)


def _documents(claim: Claim) -> set[str]:
    return {citation.doc_id for citation in claim.citations}


def _numbered(claims: list[Claim]) -> str:
    lines = ["Claims:"]
    for number, claim in enumerate(claims, start=1):
        source = _source(claim)
        lines.append(
            f'<claim n="{number}" document="{source.doc_id}" kind="{source.kind}" '
            f'date="{source.effective_date}">{claim.text}</claim>'
        )
    return "\n".join(lines)


def _judge_prompt(a: Claim, b: Claim, passages: dict[str, Chunk]) -> str:
    lines = [
        f"Claim A ({_source(a).doc_id}): {a.text}",
        f"Claim B ({_source(b).doc_id}): {b.text}",
        "",
        "Passages from other documents:",
    ]
    for chunk in passages.values():
        lines.append(f'<chunk id="{chunk.id}">\n{chunk.text}\n</chunk>')
    return "\n".join(lines)
