"""How does one domain agent answer its sub-question from its own documents?

    orchestrator -- AgentTask --> DomainAgent.answer(task)
        1. search: the store returns this domain's best chunks that the
           caller may read, in hybrid order; learned weights (learning.py)
           move rated chunks up or down
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
from rag_system.learning import ChunkWeights
from rag_system.messages import (
    AgentAnswer,
    AgentTask,
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
When two chunks disagree, write each as its own claim. If no chunk helps
answer the sub-question, return no claims.
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


# The values decided in dynamic retrieval. They are set per domain and are
# equal for now: no measurement shows a reason for different values.
DEFAULT_RETRIEVAL = RetrievalParams()
# Hits read from the store before weights reorder them: a chunk with a high
# learned weight can come up from below the first max_chunks.
CANDIDATES = 40
RETRIEVAL_BY_DOMAIN = {domain: DEFAULT_RETRIEVAL for domain in Domain}


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
        weights: ChunkWeights | None = None,
    ) -> None:
        self.domain = domain
        self._store = store
        self._model = model
        self._params = params
        self._timeout_seconds = timeout_seconds
        self._weights = weights  # None: no feedback, every chunk weighs 1.0

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
        #    hits: the 10 best technical chunks in hybrid order (no feedback
        #    yet, so every weight is 1.0), each with its embedding
        #    similarity to the sub-question:
        #      TEC-1#4 0.33, TEC-3#5 0.31, TEC-3#6 0.42, TEC-9#7 0.31,
        #      TEC-9#4 0.25, TEC-3#1 0.34, TEC-3#4 0.31, ... (10 in all)
        hits = self._store.search(
            task.sub_query.text,
            self.domain,
            task.clearance,
            limit=CANDIDATES,
            include_superseded=task.sub_query.include_history,
        )
        hits = self._weighted(task.question, hits)[: self._params.max_chunks]

        # 2. Keep the chunks that match the sub-question; if even the best
        #    one is too far from it, this domain has nothing to add.
        best = max((hit.similarity for hit in hits), default=0.0)
        if best < self._params.min_similarity:
            return self._nothing_relevant(best if hits else None)
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
            citations = [chunks[chunk_id].citation() for chunk_id in draft.chunk_ids]
            claims.append(Claim(text=draft.text, citations=citations))
        #    Example: "TEC-3#5" becomes Citation(doc_id="TEC-3",
        #      chunk_id="TEC-3#5", title="Production Release Standard",
        #      section="Release windows",
        #      version=2, effective_date=2026-02-01, kind=standard,
        #      owner="Platform Engineering").
        #    Returned: AgentAnswer(domain=technical, status=answered,
        #      3 claims, best_similarity=0.42, chunks_read=3).
        if not claims:  # the model found no answer in the chunks
            return self._nothing_relevant(best, chunks_read=len(chunks))
        return AgentAnswer(
            domain=self.domain,
            status=Status.ANSWERED,
            claims=claims,
            best_similarity=best,
            chunks_read=len(chunks),
        )

    def _nothing_relevant(
        self, best: float | None, chunks_read: int = 0
    ) -> AgentAnswer:
        return AgentAnswer(
            domain=self.domain,
            status=Status.NOTHING_RELEVANT,
            claims=[],
            best_similarity=best,
            chunks_read=chunks_read,
        )

    def _failed(self, error: str) -> AgentAnswer:
        return AgentAnswer(
            domain=self.domain,
            status=Status.FAILED,
            claims=[],
            error=error,
        )

    def _weighted(self, question: str, hits: list[Hit]) -> list[Hit]:
        """Hits reordered by (position + 1) / weight, each similarity x weight.

        With every weight at 1.0 the order and the similarities stay as the
        store returned them.
        """
        if self._weights is None:
            return hits
        weights = self._weights.for_question(question)
        scored = []
        for position, hit in enumerate(hits):
            weight = weights.weight(hit.chunk.id)
            similarity = min(1.0, hit.similarity * weight)
            scored.append(((position + 1) / weight, position, hit, similarity))
        scored.sort(key=lambda item: item[:2])
        return [
            Hit(chunk=hit.chunk, similarity=similarity)
            for _, _, hit, similarity in scored
        ]

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
