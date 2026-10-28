"""Which domains does a question need, and what does each one get asked?

    orchestrator -- question, clearance --> QueryClassifier.classify(...)
        1. search: the store returns the 8 chunks of the whole corpus
           nearest in meaning (embeddings only, not hybrid) that the
           caller may read, each from one domain
        2. the model reads the question and those chunks and returns a
           Plan: one SubQuery (domain, text) per domain to ask
    orchestrator <-- Plan --

The search runs in both modes, so the model decides from what the corpus
holds, not from the question alone. Without a key the model is the offline
stand-in (offline_model.py): it asks every domain that holds at least one
of the 8 chunks, and each domain gets the whole question.
"""

from pydantic_ai import Agent, ToolOutput
from pydantic_ai.models import Model

from rag_system.ingestion import Chunk
from rag_system.messages import Clearance, Plan
from rag_system.vector_store import Ranking, VectorStore

INSTRUCTIONS = """\
You route questions for a bank's automation platform assistant. Three
domain agents can answer: technical, business and compliance. The prompt
holds the question and the chunks of the documentation nearest to it, each
with its domain. Return a plan that asks every domain whose documents are
needed for a full answer. For each domain write the sub-question that
domain's agent should answer, using the words of the question. Set
include_history only when the question asks about the past or an old
version (for example "in 2025" or "before the change").
"""

# The model boundary: each run gets its model from the QueryClassifier.
# The model returns the plan by calling an output tool named "plan".
planner = Agent(output_type=ToolOutput(Plan, name="plan"), instructions=INSTRUCTIONS)


class QueryClassifier:
    def __init__(
        self,
        store: VectorStore,
        model: Model,
        chunks_to_read: int = 8,
        timeout_seconds: float = 30.0,
    ):
        self._store = store
        self._model = model
        self._chunks_to_read = chunks_to_read
        self._timeout_seconds = timeout_seconds

    async def classify(self, question: str, clearance: Clearance) -> Plan:
        """Steps 1-2 of the map.

        The "Example" comments follow Q01 of the eval set (the first test
        scenario of the assignment), clearance internal, offline model.
        tests/evals/test_classifier.py checks that they are still true.
        """
        # 1. Search the whole corpus, ranked by meaning only: the rule for
        #    choosing domains was measured with this ranking.
        #    Example: question is "What's the process for deploying a new
        #      microservice and what compliance checks are needed?"
        hits = self._store.search(
            question,
            domain=None,
            clearance=clearance,
            limit=self._chunks_to_read,
            ranking=Ranking.EMBEDDING,
        )
        #    hits: the 8 nearest chunks, nearest first, with their domain
        #    and their similarity to the question:
        #      1. TEC-1#1  technical   0.75
        #      2. CMP-4#1  compliance  0.60
        #      3. TEC-3#4  technical   0.59
        #      4. TEC-1#2  technical   0.58
        #      5. TEC-1#5  technical   0.54
        #      6. TEC-1#3  technical   0.54
        #      7. CMP-4#2  compliance  0.53
        #      8. TEC-1#4  technical   0.53
        #    No business chunk is among them, so business is not asked.

        # 2. The model returns the plan.
        chunks = [hit.chunk for hit in hits]
        result = await planner.run(
            _prompt(question, chunks),
            model=self._model,
            timeout=self._timeout_seconds,
        )
        #    Example: the prompt is
        #      Question: What's the process for deploying a new microservice
        #                and what compliance checks are needed?
        #
        #      Nearest chunks, nearest first:
        #      <chunk id="TEC-1#1" domain="technical">
        #      (the document title, the heading, the text of the chunk)
        #      </chunk>
        #      ... the same for the other 7
        #    result.output, from the offline model: the domains of the
        #    chunks, each with the whole question:
        #      Plan(sub_queries=[SubQuery(domain=technical, text=<question>),
        #                        SubQuery(domain=compliance, text=<question>)])
        return result.output


def _prompt(question: str, chunks: list[Chunk]) -> str:
    lines = [f"Question: {question}", "", "Nearest chunks, nearest first:"]
    for chunk in chunks:
        lines.append(
            f'<chunk id="{chunk.id}" domain="{chunk.document.domain}">\n'
            f"{chunk.text}\n</chunk>"
        )
    return "\n".join(lines)
