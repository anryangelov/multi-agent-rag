"""Shared test setup."""

from pathlib import Path

import pytest
from pydantic_ai import models

from rag_system.config import LLMProvider, Settings, build_embedder
from rag_system.ingestion import chunk_document, load_documents
from rag_system.vector_store import Embedder, InMemoryVectorStore

# A safety catch from the PydanticAI testing guide: a test that builds a real
# model (Anthropic, Azure) and runs it fails at once instead of calling out.
# FunctionModel, the offline stand-in, is allowed.
models.ALLOW_MODEL_REQUESTS = False

ROOT = Path(__file__).parents[1]


def pytest_collection_modifyitems(config, items):
    """LLM evals (`@pytest.mark.eval`) run only when .env chooses a model
    provider; Settings fails loudly if that provider has no key."""
    if Settings().llm_provider is not LLMProvider.OFFLINE:
        return
    skip = pytest.mark.skip(reason="LLM eval: set LLM_PROVIDER and its key in .env")
    for item in items:
        if item.get_closest_marker("eval"):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def local_embedder() -> Embedder:
    """The real local embedding model, loaded once."""
    return build_embedder(Settings(_env_file=None))


@pytest.fixture(scope="session")
def corpus_store(local_embedder) -> InMemoryVectorStore:
    """The real corpus indexed with the real local embedding model, built once."""
    store = InMemoryVectorStore(local_embedder)
    for document in load_documents(ROOT / "data"):
        store.add(chunk_document(document))
    return store
