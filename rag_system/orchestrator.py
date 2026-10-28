"""START HERE. What happens when a question arrives?

    caller -- question, clearance --> Orchestrator.answer(...)
        1. classify: the QueryClassifier returns a Plan, one SubQuery per
           domain to ask (query_classifier.py)
        2. ask the agents: each domain of the plan gets an AgentTask; the
           domain agents run in parallel and return AgentAnswers
           (domain_agents.py)
        3. check conflicts: the ConflictChecker finds claims that
           contradict each other and settles each pair (conflicts.py)
        4. synthesise: the model writes one answer from the claims that
           stand, plus each conflict and its reason, citing document ids
           such as [TEC-3]; code checks that every cited id was given, and
           asks the model again if not
        5. sources: code lists each cited document and section (title,
           version, date) from the claims' and the conflicts' citations
    caller <-- FinalAnswer --

Every answer is recorded, with its durations, by the Monitor if one is
given (monitoring.py).

The route is the model's decision (step 1); the order of the steps is
this code. Agents never talk to each other: every message goes through
here (messages.py).
"""

import asyncio
import re
import time
from collections.abc import Callable

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model

from rag_system.conflicts import ConflictChecker
from rag_system.domain_agents import RETRIEVAL_BY_DOMAIN, DomainAgent
from rag_system.learning import ChunkWeights
from rag_system.messages import (
    AgentAnswer,
    AgentTask,
    Citation,
    Claim,
    Clearance,
    Conflict,
    FinalAnswer,
    Status,
)
from rag_system.monitoring import Monitor
from rag_system.query_classifier import QueryClassifier
from rag_system.vector_store import VectorStore

SYNTHESIS_INSTRUCTIONS = """\
You write the final answer of a bank's automation platform assistant. The
prompt holds the question and the claims of the domain agents, each with
the ids of its source documents. Write one answer from these claims only.
After each statement cite its documents in brackets, e.g. [TEC-3]; cite
only ids given in the prompt. The prompt may also hold conflicts the
system has settled: say which rule applies, name the overruled claim and
give the reason. For a conflict with no winner, give both claims and say
who must resolve it.
"""

NOTHING_FOUND = "The documentation holds nothing that answers this question."

# A cited document id in the answer text, e.g. [TEC-3].
_CITED_ID = re.compile(r"\[([A-Z]{3}-\d+)\]")

# The model boundary of step 3: each run gets its model from the
# Orchestrator; its deps are the ids of the documents the claims cite.
synthesizer = Agent(deps_type=set[str], instructions=SYNTHESIS_INSTRUCTIONS)


@synthesizer.output_validator
def cites_only_given_documents(ctx: RunContext[set[str]], text: str) -> str:
    """Send an answer back to the model if it cites a document no claim cites."""
    for doc_id in _CITED_ID.findall(text):
        if doc_id not in ctx.deps:
            given = ", ".join(sorted(ctx.deps))
            raise ModelRetry(f"[{doc_id}] is not among the sources; cite only {given}")
    return text


class Orchestrator:
    def __init__(
        self,
        store: VectorStore,
        model: Model,
        weights: ChunkWeights | None = None,
        monitor: Monitor | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        """`weights`: what feedback has taught (learning.py), shared by all
        agents; without it every chunk weighs 1.0. `monitor` records every
        answer; `clock` measures its durations, in seconds."""
        self._store = store
        self._model = model
        self._monitor = monitor
        self._clock = clock
        self._classifier = QueryClassifier(store, model)
        self._conflicts = ConflictChecker(store, model)
        self._agents = {}
        for domain, params in RETRIEVAL_BY_DOMAIN.items():
            self._agents[domain] = DomainAgent(
                domain, store, model, params, weights=weights
            )

    async def answer(self, question: str, clearance: Clearance) -> FinalAnswer:
        """Steps 1-5 of the map.

        The "Example" comments follow Q01 of the eval set (the first test
        scenario of the assignment), clearance internal, offline model.
        tests/test_scenarios.py checks that they are still true.
        """
        started = self._clock()
        # 1. Classify: which domains, and what each is asked.
        #    Example: question is "What's the process for deploying a new
        #      microservice and what compliance checks are needed?"
        plan = await self._classifier.classify(question, clearance)
        #    plan: technical and compliance, each with the whole question.

        # 2. Ask the agents of the plan, in parallel.
        calls = []
        for sub_query in plan.sub_queries:
            task = AgentTask(
                question=question, sub_query=sub_query, clearance=clearance
            )
            calls.append(self._timed(self._agents[sub_query.domain], task))
        timed = await asyncio.gather(*calls)
        agent_answers = [agent_answer for agent_answer, _ in timed]
        #    Example: two AgentAnswers, in the order of the plan:
        #      technical   answered  10 claims, e.g. "1. Register the service
        #                  in the service catalog." citing TEC-1
        #      compliance  answered   8 claims

        # 3. Check whether claims contradict each other.
        claims = _claims(agent_answers)
        conflicts = []
        if len(claims) > 1:
            conflicts = await self._conflicts.check(claims, clearance)
        #    Example: offline, no conflict is found (detecting one needs a
        #    language model).

        # 4. Synthesise one answer from the claims that stand.
        if claims:
            text = await self._synthesise(question, agent_answers, conflicts)
        else:
            text = NOTHING_FOUND
        #    Example: the synthesis prompt holds the question and the 18
        #    claims, one per line:
        #      <claim domain="technical" sources="TEC-1">1. Register the
        #      service in the service catalog.</claim>
        #    text, from the offline model: a note that no language model was
        #    used, then one paragraph per domain, each claim followed by its
        #    documents:
        #      Technical: This guide walks a development team through the
        #      first deployment of a new microservice on the automation
        #      platform. [TEC-1] ...

        # 5. List the sources the answer cites.
        #    Example: 18 sources, each document and section once, in the
        #    order the text cites them: TEC-1 (no section), TEC-1 "Typical
        #    first-release timeline", ... , CMP-4 "When to repeat".
        final = FinalAnswer(
            question=question,
            plan=plan,
            agent_answers=agent_answers,
            text=text,
            sources=_sources(text, claims, conflicts),
            conflicts=conflicts,
        )
        if self._monitor is not None:
            agent_seconds = {a.domain: seconds for a, seconds in timed}
            seconds = self._clock() - started
            self._monitor.record(final, seconds, agent_seconds, self._store.model)
        return final

    async def _timed(
        self, agent: DomainAgent, task: AgentTask
    ) -> tuple[AgentAnswer, float]:
        started = self._clock()
        agent_answer = await agent.answer(task)
        return agent_answer, self._clock() - started

    async def _synthesise(
        self,
        question: str,
        agent_answers: list[AgentAnswer],
        conflicts: list[Conflict],
    ) -> str:
        given = set()
        for citation in _citations(_claims(agent_answers), conflicts):
            given.add(citation.doc_id)
        result = await synthesizer.run(
            _prompt(question, agent_answers, conflicts), model=self._model, deps=given
        )
        return result.output


def _claims(agent_answers: list[AgentAnswer]) -> list[Claim]:
    claims = []
    for agent_answer in agent_answers:
        if agent_answer.status is Status.ANSWERED:
            claims.extend(agent_answer.claims)
    return claims


def _prompt(
    question: str, agent_answers: list[AgentAnswer], conflicts: list[Conflict]
) -> str:
    """The claims that stand, one per line; then each conflict, settled."""
    overruled = [conflict.loser for conflict in conflicts if conflict.loser]
    lines = [f"Question: {question}", "", "Claims of the domain agents:"]
    for agent_answer in agent_answers:
        for claim in agent_answer.claims:
            if claim not in overruled:
                lines.append(
                    f'<claim domain="{agent_answer.domain}" '
                    f'sources="{" ".join(_doc_ids(claim))}">{claim.text}</claim>'
                )
    for conflict in conflicts:
        lines.append(f"<conflict>{_settled(conflict)}</conflict>")
    return "\n".join(lines)


def _settled(conflict: Conflict) -> str:
    """One sentence that says how a conflict was settled, with its sources."""
    a, b, loser = conflict.claim_a, conflict.claim_b, conflict.loser
    if loser is None:
        sentence = (
            f'Unresolved: "{a.text}" {_cited(a)} and "{b.text}" {_cited(b)} '
            f"disagree; {conflict.reason}."
        )
    else:
        sentence = f'Overruled: "{loser.text}" {_cited(loser)}; {conflict.reason}.'
    if conflict.evidence:
        evidence = {citation.doc_id: None for citation in conflict.evidence}
        sentence += " Supported by " + " ".join(f"[{d}]" for d in evidence) + "."
    return sentence


def _doc_ids(claim: Claim) -> list[str]:
    doc_ids = []
    for citation in claim.citations:
        if citation.doc_id not in doc_ids:
            doc_ids.append(citation.doc_id)
    return doc_ids


def _cited(claim: Claim) -> str:
    return " ".join(f"[{doc_id}]" for doc_id in _doc_ids(claim))


def _citations(claims: list[Claim], conflicts: list[Conflict]) -> list[Citation]:
    """Every citation the answer may use: the claims' and the evidence's."""
    citations = [citation for claim in claims for citation in claim.citations]
    for conflict in conflicts:
        citations.extend(conflict.evidence)
    return citations


def _sources(
    text: str, claims: list[Claim], conflicts: list[Conflict]
) -> list[Citation]:
    """Each cited document and section once, in the order the text cites them."""
    sources = []
    for doc_id in _CITED_ID.findall(text):
        for citation in _citations(claims, conflicts):
            if citation.doc_id == doc_id and citation not in sources:
                sources.append(citation)
    return sources
