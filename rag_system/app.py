"""How is the system put together, and how do I ask it something?

    Assistant(settings)
      1. Settings() reads .env: which language model, which embedding model
      2. build_llm, build_embedder: the two models
      3. load_documents(data/), chunk_document, store.add: the index
      4. Orchestrator(store, model, monitor): the system (orchestrator.py)
    await assistant.ask(question)  --> FinalAnswer
    as_markdown(answer)            --> the answer, its sources and warnings

The notebook and the command line (`python -m rag_system`) both start here,
so they run the same system. This is the one place that builds the models
from settings; everything below receives them as parameters.
"""

from pathlib import Path

from rag_system.config import LLMProvider, Settings, build_embedder, build_llm
from rag_system.ingestion import chunk_document, load_documents
from rag_system.messages import Classification, FinalAnswer
from rag_system.monitoring import Monitor
from rag_system.orchestrator import Orchestrator
from rag_system.vector_store import InMemoryVectorStore

DATA = Path(__file__).parents[1] / "data"


class Assistant:
    def __init__(
        self,
        settings: Settings | None = None,
        data: Path = DATA,
        timeout_seconds: float = 60.0,
    ) -> None:
        # 1. .env chooses the models; without it, the offline stand-in.
        self.settings = settings or Settings()
        # 2. The two models.
        self.model = build_llm(self.settings)
        self.embedder = build_embedder(self.settings)
        # 3. The index of every document.
        self.documents = load_documents(data)
        self.store = self.new_store()
        # 4. The system, recording every answer.
        self.monitor = Monitor()
        self.orchestrator = Orchestrator(
            self.store,
            self.model,
            monitor=self.monitor,
            timeout_seconds=timeout_seconds,
        )

    async def ask(
        self, question: str, clearance: Classification = Classification.INTERNAL
    ) -> FinalAnswer:
        return await self.orchestrator.answer(question, clearance)

    def new_store(self) -> InMemoryVectorStore:
        """A fresh index of the documents, e.g. to try a knowledge update on."""
        store = InMemoryVectorStore(self.embedder)
        for document in self.documents:
            store.add(chunk_document(document))
        return store

    def describe(self) -> str:
        """Which models run, in two lines."""
        if self.settings.llm_provider is LLMProvider.OFFLINE:
            language = (
                "the OFFLINE stand-in (no key in .env); answers are templates "
                "built from the retrieved chunks, not model writing"
            )
        else:
            language = f"{self.settings.llm_provider} ({self.model.model_name})"
        return f"Language model: {language}\nEmbedding model: {self.store.model}"


def as_markdown(answer: FinalAnswer) -> str:
    """The answer text, then its sources and any warnings, as Markdown."""
    lines = [answer.text, "", "**Sources**", ""]
    for source in answer.sources:
        section = f', "{source.section}"' if source.section else ""
        lines.append(
            f"- [{source.doc_id}] {source.title}, v{source.version}, "
            f"{source.effective_date}{section}"
        )
    if answer.warnings:
        lines += ["", "**Warnings**", ""]
        lines += [f"- {warning}" for warning in answer.warnings]
    return "\n".join(lines)
