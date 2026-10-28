"""What do the agents send each other? (the agent communication protocol)

The orchestrator is the hub; agents never talk to each other.

    classifier ---- Plan --------------------------> orchestrator
                    one SubQuery per chosen domain

    orchestrator -- AgentTask ---------------------> each domain agent
                    question, sub-query, clearance     (in parallel)

    domain agent -- AgentAnswer -------------------> orchestrator
                    status, claims, confidence
                    each Claim cites one or more Citations

    orchestrator -- FinalAnswer -------------------> caller
                    the answer text citing [TEC-3], its sources, and the
                    plan and partial results it was made from

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
    title: str
    section: str | None
    version: int
    effective_date: date
    kind: Kind


class Claim(_Message):
    """One statement an agent makes, with its sources."""

    text: str
    citations: list[Citation] = Field(min_length=1)


class AgentAnswer(_Message):
    """The partial result a domain agent sends back up."""

    domain: Domain
    status: Status
    claims: list[Claim]
    confidence: float = Field(ge=0, le=1)
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


class FinalAnswer(_Message):
    """What the orchestrator returns: one answer, its sources, how it was made."""

    question: str
    plan: Plan
    agent_answers: list[AgentAnswer]
    text: str  # cites document ids in brackets, e.g. [TEC-3]
    sources: list[Citation]  # each cited document and section, once
