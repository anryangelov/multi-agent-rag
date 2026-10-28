"""What do the agents send each other? (the agent communication protocol)

The orchestrator is the hub; agents never talk to each other.

    classifier ---- Plan --------------------------> orchestrator
                    one SubQuery per chosen domain

    orchestrator -- AgentTask ---------------------> each domain agent
                    question, sub-query, clearance     (in parallel)

    domain agent -- AgentAnswer -------------------> orchestrator
                    status, claims, best similarity
                    each Claim cites one or more Citations

    orchestrator -- claims, clearance -------------> conflict checker
    conflict checker -- Conflict, Conflict, ... ----> orchestrator
                    two claims, the decision, the scores and the reason

    orchestrator -- FinalAnswer -------------------> caller
                    the answer text citing [TEC-3], its sources, its
                    conflicts, and the plan and partial results it was
                    made from

Every message is frozen: whoever receives it cannot change it.
"""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Domain(StrEnum):
    TECHNICAL = "technical"
    BUSINESS = "business"
    COMPLIANCE = "compliance"

    @property
    def prefix(self) -> str:
        """The prefix of this domain's document ids: TEC-1, BUS-1, CMP-1."""
        return {"technical": "TEC", "business": "BUS", "compliance": "CMP"}[self]


class Kind(StrEnum):
    POLICY = "policy"
    STANDARD = "standard"
    GUIDE = "guide"
    RUNBOOK = "runbook"
    REPORT = "report"

    @property
    def rank(self) -> int:
        """Authority in a conflict between documents of different kinds.

        A policy overrules a standard, a standard a guide, a guide a
        runbook. A report holds facts, not rules, so it ranks lowest.
        """
        return {
            "policy": 4,
            "standard": 3,
            "guide": 2,
            "runbook": 1,
            "report": 0,
        }[self]


class Classification(StrEnum):
    """One scale for two things: a document's class and a caller's clearance."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"

    def allows(self, document: "Classification") -> bool:
        """Whether a caller with this clearance may read a document of that class."""
        order = list(Classification)
        return order.index(document) <= order.index(self)


# A caller's clearance is a level on the same scale as a document's class;
# the separate name says which role a value plays.
Clearance = Classification


class Status(StrEnum):
    ANSWERED = "answered"
    NOTHING_RELEVANT = "nothing_relevant"
    FAILED = "failed"


class _Message(BaseModel):
    model_config = ConfigDict(frozen=True)


class SubQuery(_Message):
    """What one domain agent is asked."""

    domain: Domain
    text: str
    include_history: bool = Field(
        default=False,
        description="True when the question asks about the past or an old "
        "version, e.g. 'in 2025'; the search then includes superseded versions.",
    )


class Plan(_Message):
    """The classifier's decision: which domains to ask, and what."""

    sub_queries: list[SubQuery] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_sub_query_per_domain(self) -> "Plan":
        domains = [sub.domain for sub in self.sub_queries]
        if len(domains) != len(set(domains)):
            raise ValueError("a plan asks a domain more than once")
        return self


class AgentTask(_Message):
    """The context the orchestrator sends down to one domain agent."""

    question: str
    sub_query: SubQuery
    clearance: Clearance


class Citation(_Message):
    """Where a claim comes from: one document, and the section if it has one."""

    doc_id: str = Field(pattern=r"^(TEC|BUS|CMP)-\d+$")
    chunk_id: str  # the exact piece, e.g. "TEC-3#5": what feedback rates
    title: str
    section: str | None
    version: int
    effective_date: date
    kind: Kind
    owner: str  # who must fix the document if it is wrong


class Claim(_Message):
    """One statement an agent makes, with its sources."""

    text: str
    citations: list[Citation] = Field(min_length=1)


class AgentAnswer(_Message):
    """The partial result a domain agent sends back up."""

    domain: Domain
    status: Status
    claims: list[Claim]
    # The cosine similarity of the agent's best chunk to its sub-question:
    # how close the text came, not how sure the answer is. None when the
    # agent failed or found no chunk.
    best_similarity: float | None = Field(default=None, ge=-1, le=1)
    error: str | None = None

    @model_validator(mode="after")
    def _fields_match_status(self) -> "AgentAnswer":
        if self.status is Status.ANSWERED and not self.claims:
            raise ValueError("an answered result needs at least one claim")
        if self.status is not Status.ANSWERED and self.claims:
            raise ValueError(f"a {self.status} result carries no claims")
        if (self.status is Status.FAILED) != (self.error is not None):
            raise ValueError("a failed result, and only a failed one, has an error")
        return self


class Decision(StrEnum):
    """How a conflict between two claims was settled."""

    KIND = "kind"  # the documents differ in kind: the stronger kind won
    EVIDENCE = "evidence"  # same kind: more other documents support the winner
    NO_WINNER = "no_winner"  # same kind, and the evidence is even


class Conflict(_Message):
    """Two claims that contradict each other, and how the conflict was settled.

    The scores are the kinds' ranks (Decision.KIND) or the number of other
    documents that support each claim; the higher score wins.
    """

    topic: str
    claim_a: Claim
    claim_b: Claim
    decision: Decision
    score_a: int
    score_b: int
    reason: str  # e.g. "CMP-3 (policy) overrules TEC-4 (runbook)"
    evidence: list[Citation] = []  # the other documents that support a side

    @property
    def winner(self) -> Claim | None:
        if self.score_a > self.score_b:
            return self.claim_a
        if self.score_b > self.score_a:
            return self.claim_b
        return None

    @property
    def loser(self) -> Claim | None:
        if self.winner is None:
            return None
        return self.claim_b if self.winner is self.claim_a else self.claim_a

    @model_validator(mode="after")
    def _decision_matches_scores(self) -> "Conflict":
        if (self.decision is Decision.NO_WINNER) != (self.score_a == self.score_b):
            raise ValueError("a conflict has no winner exactly when its scores tie")
        return self


class FinalAnswer(_Message):
    """What the orchestrator returns: one answer, its sources, how it was made."""

    question: str
    plan: Plan
    agent_answers: list[AgentAnswer]
    text: str  # cites document ids in brackets, e.g. [TEC-3]
    sources: list[Citation]  # each cited document and section, once
    conflicts: list[Conflict] = []  # contradicting claims and their outcome
