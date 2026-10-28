"""How does one domain agent answer its sub-question from its own documents?

    orchestrator -- AgentTask --> DomainAgent.answer(task)
        1. search: the store returns this domain's best chunks that the
           caller may read, in hybrid order
        2. keep the chunks that match the question (dynamic retrieval)
        3. the model reads the kept chunks and writes claims, each citing
           the ids of the chunks it comes from
        4. code turns each chunk id into a Citation (document, section,
           version, date, kind), so no citation is written by the model
    orchestrator <-- AgentAnswer --

Other endings:
    the best chunk is below 0.4, or the model writes no claim
        --> status nothing_relevant: this domain has nothing to add
    any step fails or the time runs out
        --> status failed, with the error; the other agents go on

Without a key the model is the offline stand-in (offline_model.py), which
writes one claim per chunk by template.
"""

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, ModelRetry, RunContext, ToolOutput
from pydantic_ai.models import Model

from rag_system.ingestion import Chunk
from rag_system.messages import (
    AgentAnswer,
    AgentTask,
    Citation,
    Claim,
    Domain,
    Status,
)
from rag_system.vector_store import Hit, VectorStore

INSTRUCTIONS = """\
You are a domain agent of a bank's automation platform assistant. The
prompt names your domain. Answer the sub-question only from the chunks in
the prompt. Write short claims. Each claim cites the ids of the chunks it
comes from, e.g. "TEC-3#2". Do not add facts that are not in the chunks.
If no chunk helps answer the sub-question, return no claims.
"""


class RetrievalParams(BaseModel):
    """How many chunks an agent gives its model (decided in dynamic retrieval).

    The agent keeps chunks in hybrid order: always the first `min_chunks`,
    then every further one whose embedding similarity to the sub-question
    is at least `min_similarity`, never more than `max_chunks`.
    """

    model_config = ConfigDict(frozen=True)

    min_chunks: int = 3
    max_chunks: int = 10
    min_similarity: float = 0.4


# The values decided in dynamic retrieval; equal for every domain for now.
DEFAULT_RETRIEVAL = RetrievalParams()


class DraftClaim(BaseModel):
    """A claim as the model writes it: the text and the chunk ids it cites."""

    text: str
    chunk_ids: list[str] = Field(
        min_length=1, description='The ids of the chunks, e.g. "TEC-3#2".'
    )


class DraftAnswer(BaseModel):
    """What the model returns; code turns it into an AgentAnswer."""

    claims: list[DraftClaim]


# The model boundary, shared by the three domain agents: each run gets its
# model from the DomainAgent, and its deps are the kept chunks by id, the
# only chunks the model may cite. The model returns its claims by calling
# an output tool named "claims".
claims_writer = Agent(
    deps_type=dict[str, Chunk],
    output_type=ToolOutput(DraftAnswer, name="claims"),
    instructions=INSTRUCTIONS,
)


@claims_writer.output_validator
def cites_only_given_chunks(
    ctx: RunContext[dict[str, Chunk]], draft: DraftAnswer
) -> DraftAnswer:
    """Send a draft back to the model if it cites a chunk it was not given."""
    for claim in draft.claims:
        for chunk_id in claim.chunk_ids:
            if chunk_id not in ctx.deps:
                given = ", ".join(ctx.deps)
                raise ModelRetry(f"{chunk_id} was not given; cite only: {given}")
    return draft


class DomainAgent:
    def __init__(
        self,
        domain: Domain,
        store: VectorStore,
        model: Model,
        params: RetrievalParams = DEFAULT_RETRIEVAL,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.domain = domain
        self._store = store
        self._model = model
        self._params = params
        self._timeout_seconds = timeout_seconds

    async def answer(self, task: AgentTask) -> AgentAnswer:
        """Answer the task; a failure or a timeout becomes status `failed`.

        One agent's failure must not stop the others, so every error ends
        here as an answer the orchestrator can report.
        """
        try:
            return await self._steps(task)
        except TimeoutError:  # RunTimedOut from the model run is a TimeoutError
            return self._failed(f"timed out after {self._timeout_seconds} s")
        except Exception as error:
            return self._failed(f"{type(error).__name__}: {error}")

    async def _steps(self, task: AgentTask) -> AgentAnswer:
        """Steps 1-4 of the map; any error goes up to `answer`.

        The "Example" comments follow one real question through the steps:
        Q04 of the eval set, asked to the technical agent, offline model.
        tests/evals/test_retrieval.py checks that they are still true.
        """
        # 1. Search this domain's chunks that the caller may read.
        #    Example: task.sub_query.text is
        #      "Is one sign-off enough to ship a change to production?"
        #    hits: the 10 best technical chunks in hybrid order, each with its
        #    embedding similarity to the sub-question:
        #      TEC-1#4 0.33, TEC-3#5 0.31, TEC-3#6 0.42, TEC-9#7 0.31,
        #      TEC-9#4 0.25, TEC-3#1 0.34, TEC-3#4 0.31, ... (10 in all)
        hits = self._store.search(
            task.sub_query.text,
            self.domain,
            task.clearance,
            limit=self._params.max_chunks,
        )

        # 2. Keep the chunks that match the sub-question; if even the best
        #    one is too far from it, this domain has nothing to add.
        best = max((hit.similarity for hit in hits), default=0.0)
        if best < self._params.min_similarity:
            return self._nothing_relevant()
        kept = self._keep(hits)
        chunks = {hit.chunk.id: hit.chunk for hit in kept}
        #    Example: best is 0.42 (TEC-3#6), not below 0.4, so the agent
        #    goes on. kept: the first 3 always (TEC-1#4, TEC-3#5, TEC-3#6);
        #    none of the other 7 reaches 0.4, so they are left out, also
        #    TEC-3#4 (section "Approvals", 0.31).

        # 3. The model writes claims that cite chunk ids.
        result = await claims_writer.run(
            _prompt(self.domain, task, list(chunks.values())),
            model=self._model,
            deps=chunks,
            timeout=self._timeout_seconds,
        )
        #    Example: the prompt is
        #      Domain: technical
        #      Question: Is one sign-off enough to ship a change to production?
        #      Sub-question: (the same text)
        #
        #      Chunks:
        #      <chunk id="TEC-1#4">
        #      (the document title, the heading, the text of the chunk)
        #      </chunk>
        #      ... the same for TEC-3#5 and TEC-3#6
        #    result.output, from the offline model: one claim per chunk,
        #      DraftClaim(text="Releases happen from Tuesday to Thursday,
        #                 09:00 to 15:00.", chunk_ids=["TEC-3#5"]), ...

        # 4. Code turns each cited chunk id into a Citation.
        claims = []
        for draft in result.output.claims:
            citations = [_citation(chunks[chunk_id]) for chunk_id in draft.chunk_ids]
            claims.append(Claim(text=draft.text, citations=citations))
        #    Example: "TEC-3#5" becomes Citation(doc_id="TEC-3",
        #      title="Production Release Standard", section="Release windows",
        #      version=2, effective_date=2026-02-01, kind=standard).
        #    Returned: AgentAnswer(domain=technical, status=answered,
        #      3 claims, confidence=0.42).
        if not claims:  # the model found no answer in the chunks
            return self._nothing_relevant()
        return AgentAnswer(
            domain=self.domain,
            status=Status.ANSWERED,
            claims=claims,
            # Placeholder until the confidence rules of phase 3.
            confidence=best,
        )

    def _nothing_relevant(self) -> AgentAnswer:
        return AgentAnswer(
            domain=self.domain,
            status=Status.NOTHING_RELEVANT,
            claims=[],
            confidence=0.0,
        )

    def _failed(self, error: str) -> AgentAnswer:
        return AgentAnswer(
            domain=self.domain,
            status=Status.FAILED,
            claims=[],
            confidence=0.0,
            error=error,
        )

    def _keep(self, hits: list[Hit]) -> list[Hit]:
        kept = []
        for position, hit in enumerate(hits):
            if position < self._params.min_chunks:
                kept.append(hit)
            elif hit.similarity >= self._params.min_similarity:
                kept.append(hit)
        return kept


def _prompt(domain: Domain, task: AgentTask, chunks: list[Chunk]) -> str:
    lines = [
        f"Domain: {domain}",
        f"Question: {task.question}",
        f"Sub-question: {task.sub_query.text}",
        "",
    ]
    lines.append("Chunks:")
    for chunk in chunks:
        lines.append(f'<chunk id="{chunk.id}">\n{chunk.text}\n</chunk>')
    return "\n".join(lines)


def _citation(chunk: Chunk) -> Citation:
    document = chunk.document
    return Citation(
        doc_id=document.id,
        title=document.title,
        section=chunk.section,
        version=document.version,
        effective_date=document.effective_date,
        kind=document.kind,
    )
