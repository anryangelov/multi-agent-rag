"""START HERE. What happens when a question arrives?

    caller -- question, clearance --> Orchestrator.answer(...)
        1. classify: the QueryClassifier returns a Plan, one SubQuery per
           domain to ask (query_classifier.py)
        2. ask the agents: each domain of the plan gets an AgentTask; the
           domain agents run in parallel and return AgentAnswers
           (domain_agents.py)
        3. synthesise: the model writes one answer from the agents' claims,
           citing document ids such as [TEC-3]; code checks that every
           cited id belongs to a claim, and asks the model again if not
        4. sources: code lists each cited document and section (title,
           version, date) from the claims' citations
    caller <-- FinalAnswer --

The route is the model's decision (step 1); the order of the steps is
this code. Agents never talk to each other: every message goes through
here (messages.py). Conflicting claims are passed to the synthesis as
they are; rules to resolve them are not written yet.
"""

import asyncio
import re

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model

from rag_system.domain_agents import RETRIEVAL_BY_DOMAIN, DomainAgent
from rag_system.messages import (
    AgentAnswer,
    AgentTask,
    Citation,
    Claim,
    Clearance,
    FinalAnswer,
    Status,
)
from rag_system.query_classifier import QueryClassifier
from rag_system.vector_store import VectorStore

SYNTHESIS_INSTRUCTIONS = """\
You write the final answer of a bank's automation platform assistant. The
prompt holds the question and the claims of the domain agents, each with
the ids of its source documents. Write one answer from these claims only.
After each statement cite its documents in brackets, e.g. [TEC-3]; cite
only ids given with the claims.
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
    def __init__(self, store: VectorStore, model: Model) -> None:
        self._model = model
        self._classifier = QueryClassifier(store, model)
        self._agents = {}
        for domain, params in RETRIEVAL_BY_DOMAIN.items():
            self._agents[domain] = DomainAgent(domain, store, model, params)

    async def answer(self, question: str, clearance: Clearance) -> FinalAnswer:
        """Steps 1-4 of the map.

        The "Example" comments follow Q01 of the eval set (the first test
        scenario of the assignment), clearance internal, offline model.
        tests/test_scenarios.py checks that they are still true.
        """
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
            calls.append(self._agents[sub_query.domain].answer(task))
        agent_answers = list(await asyncio.gather(*calls))
        #    Example: two AgentAnswers, in the order of the plan:
        #      technical   answered  10 claims, e.g. "1. Register the service
        #                  in the service catalog." citing TEC-1
        #      compliance  answered   8 claims

        # 3. Synthesise one answer from the claims.
        claims = _claims(agent_answers)
        if claims:
            text = await self._synthesise(question, agent_answers, claims)
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

        # 4. List the sources the answer cites.
        #    Example: 18 sources, each document and section once, in the
        #    order the text cites them: TEC-1 (no section), TEC-1 "Typical
        #    first-release timeline", ... , CMP-4 "When to repeat".
        return FinalAnswer(
            question=question,
            plan=plan,
            agent_answers=agent_answers,
            text=text,
            sources=_sources(text, claims),
        )

    async def _synthesise(
        self, question: str, agent_answers: list[AgentAnswer], claims: list[Claim]
    ) -> str:
        given = set()
        for claim in claims:
            for citation in claim.citations:
                given.add(citation.doc_id)
        result = await synthesizer.run(
            _prompt(question, agent_answers), model=self._model, deps=given
        )
        return result.output


def _claims(agent_answers: list[AgentAnswer]) -> list[Claim]:
    claims = []
    for agent_answer in agent_answers:
        if agent_answer.status is Status.ANSWERED:
            claims.extend(agent_answer.claims)
    return claims


def _prompt(question: str, agent_answers: list[AgentAnswer]) -> str:
    lines = [f"Question: {question}", "", "Claims of the domain agents:"]
    for agent_answer in agent_answers:
        for claim in agent_answer.claims:
            doc_ids = []
            for citation in claim.citations:
                if citation.doc_id not in doc_ids:
                    doc_ids.append(citation.doc_id)
            lines.append(
                f'<claim domain="{agent_answer.domain}" '
                f'sources="{" ".join(doc_ids)}">{claim.text}</claim>'
            )
    return "\n".join(lines)


def _sources(text: str, claims: list[Claim]) -> list[Citation]:
    """Each cited document and section once, in the order the text cites them."""
    sources = []
    for doc_id in _CITED_ID.findall(text):
        for claim in claims:
            for citation in claim.citations:
                if citation.doc_id == doc_id and citation not in sources:
                    sources.append(citation)
    return sources
