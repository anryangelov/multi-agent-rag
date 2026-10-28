"""How well do the agents and the whole system answer?

    orchestrator -- FinalAnswer, durations, embedding model --> Monitor.record
        one QuestionRecord per question:
          outcome     successful: the answer cites a source, no agent failed
                      partial:    the answer cites a source, an agent failed
                      failed:     the answer cites nothing
          per agent   status, seconds, chunks read, best similarity, error
          conflicts   decided, and without a winner
    feedback -- Rating, Rating, ... --> Monitor.record_ratings
    Monitor.summary() / report()
        success rate; per agent: share answered / nothing relevant /
        failed, mean seconds, share of its sources rated useful

The records stay in memory: the demo needs one run, not a history. In
production the same records would go to OpenTelemetry, which PydanticAI
already uses for the model calls (durations, tokens).
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from rag_system.learning import Rating
from rag_system.messages import Decision, Domain, FinalAnswer, Status


class Outcome(StrEnum):
    SUCCESSFUL = "successful"
    PARTIAL = "partial"
    FAILED = "failed"


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True)


class AgentRecord(_Record):
    domain: Domain
    status: Status
    seconds: float
    chunks_read: int
    best_similarity: float | None
    error: str | None


class QuestionRecord(_Record):
    question: str
    outcome: Outcome
    seconds: float
    agents: list[AgentRecord]
    conflicts_decided: int
    conflicts_without_winner: int
    embedding_model: str


class AgentSummary(_Record):
    domain: Domain
    asked: int  # questions this agent was asked
    answered: float  # shares of `asked`
    nothing_relevant: float
    failed: float
    mean_seconds: float
    rated_useful: float | None  # share of its rated sources; None: no ratings


class Summary(_Record):
    questions: int
    success_rate: float
    agents: list[AgentSummary]  # in the order technical, business, compliance


class Monitor:
    def __init__(self) -> None:
        self.records: list[QuestionRecord] = []
        self.ratings: list[Rating] = []

    def record(
        self,
        answer: FinalAnswer,
        seconds: float,
        agent_seconds: dict[Domain, float],
        embedding_model: str,
    ) -> None:
        agents = []
        for agent_answer in answer.agent_answers:
            agents.append(
                AgentRecord(
                    domain=agent_answer.domain,
                    status=agent_answer.status,
                    seconds=agent_seconds[agent_answer.domain],
                    chunks_read=agent_answer.chunks_read,
                    best_similarity=agent_answer.best_similarity,
                    error=agent_answer.error,
                )
            )
        undecided = [c for c in answer.conflicts if c.decision is Decision.NO_WINNER]
        self.records.append(
            QuestionRecord(
                question=answer.question,
                outcome=_outcome(answer),
                seconds=seconds,
                agents=agents,
                conflicts_decided=len(answer.conflicts) - len(undecided),
                conflicts_without_winner=len(undecided),
                embedding_model=embedding_model,
            )
        )

    def record_ratings(self, ratings: list[Rating]) -> None:
        self.ratings.extend(ratings)

    def summary(self) -> Summary:
        successful = [r for r in self.records if r.outcome is Outcome.SUCCESSFUL]
        agents = []
        for domain in Domain:
            runs = [a for r in self.records for a in r.agents if a.domain is domain]
            if runs:
                agents.append(self._agent_summary(domain, runs))
        return Summary(
            questions=len(self.records),
            success_rate=len(successful) / len(self.records) if self.records else 0.0,
            agents=agents,
        )

    def report(self) -> str:
        """The summary as a plain text table, for the notebook."""
        summary = self.summary()
        lines = [
            f"questions: {summary.questions}, successful: {summary.success_rate:.0%}",
            "",
            f"{'agent':<12}{'asked':>6}{'answered':>10}{'nothing':>9}"
            f"{'failed':>8}{'seconds':>9}{'useful':>8}",
        ]
        for agent in summary.agents:
            useful = "-" if agent.rated_useful is None else f"{agent.rated_useful:.0%}"
            lines.append(
                f"{agent.domain:<12}{agent.asked:>6}{agent.answered:>10.0%}"
                f"{agent.nothing_relevant:>9.0%}{agent.failed:>8.0%}"
                f"{agent.mean_seconds:>9.2f}{useful:>8}"
            )
        return "\n".join(lines)

    def _agent_summary(self, domain: Domain, runs: list[AgentRecord]) -> AgentSummary:
        def share(status: Status) -> float:
            return sum(run.status is status for run in runs) / len(runs)

        rated = [r for r in self.ratings if r.chunk_id.startswith(domain.prefix)]
        return AgentSummary(
            domain=domain,
            asked=len(runs),
            answered=share(Status.ANSWERED),
            nothing_relevant=share(Status.NOTHING_RELEVANT),
            failed=share(Status.FAILED),
            mean_seconds=sum(run.seconds for run in runs) / len(runs),
            rated_useful=(sum(r.useful for r in rated) / len(rated) if rated else None),
        )


def _outcome(answer: FinalAnswer) -> Outcome:
    if not answer.sources:
        return Outcome.FAILED
    if any(a.status is Status.FAILED for a in answer.agent_answers):
        return Outcome.PARTIAL
    return Outcome.SUCCESSFUL
