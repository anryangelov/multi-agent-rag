"""Shared test setup."""

from pathlib import Path

import pytest
from pydantic_ai import models

from rag_system.config import Settings, build_embedder
from rag_system.ingestion import chunk_document, load_documents
from rag_system.vector_store import InMemoryVectorStore

# A safety catch from the PydanticAI testing guide: a test that builds a real
# model (Anthropic, Azure) and runs it fails at once instead of calling out.
# FunctionModel, the offline stand-in, is allowed.
models.ALLOW_MODEL_REQUESTS = False

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="session")
def corpus_store() -> InMemoryVectorStore:
    """The real corpus indexed with the real local embedding model, built once."""
    store = InMemoryVectorStore(build_embedder(Settings(_env_file=None)))
    for document in load_documents(ROOT / "data"):
        store.add(chunk_document(document))
    return store
