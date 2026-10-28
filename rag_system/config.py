"""Which models does the system use, and how are they built from settings?

The settings come from environment variables or a .env file. With neither,
the system runs offline with the local embedding model.

    Settings()
        reads LLM_PROVIDER, EMBEDDING_PROVIDER and the credentials of the
        chosen providers; a missing credential fails here, at startup

    build_llm(settings)              LLM_PROVIDER
        offline   --> FunctionModel     templates, no key (offline_model.py)
        anthropic --> AnthropicModel    the model named by ANTHROPIC_MODEL
        azure     --> OpenAIChatModel   the chat deployment, via AzureProvider

    build_embedder(settings)         EMBEDDING_PROVIDER
        local     --> Model2VecEmbedder potion-base-8M, on the CPU
        azure     --> AzureEmbedder     the embedding deployment

Nothing else in the system builds a model: every component receives the one
built here as a parameter. A new provider (e.g. a language model running
on-premise) is one enum value and one `case`.
"""

from enum import StrEnum

import numpy as np
from model2vec import StaticModel
from openai import AzureOpenAI
from pydantic import SecretStr, model_validator
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.azure import AzureProvider
from pydantic_settings import BaseSettings, SettingsConfigDict

from rag_system.offline_model import offline_model
from rag_system.vector_store import Embedder

# What both Azure models need to reach the Azure OpenAI resource.
AZURE_CONNECTION = [
    "azure_openai_api_key",
    "azure_openai_endpoint",
    "azure_openai_api_version",
]


class LLMProvider(StrEnum):
    OFFLINE = "offline"
    ANTHROPIC = "anthropic"
    AZURE = "azure"


class EmbeddingProvider(StrEnum):
    LOCAL = "local"
    AZURE = "azure"


class Settings(BaseSettings):
    # An empty line such as `ANTHROPIC_API_KEY=` in .env counts as not set.
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    llm_provider: LLMProvider = LLMProvider.OFFLINE
    embedding_provider: EmbeddingProvider = EmbeddingProvider.LOCAL

    # potion-base-8M was chosen by the embedding spike; the recorded swap,
    # if per-domain retrieval misses documents, is potion-retrieval-32M.
    local_embedding_model: str = "minishlab/potion-base-8M"

    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5-5"

    azure_openai_api_key: SecretStr | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str | None = None
    azure_openai_chat_deployment: str | None = None
    azure_openai_embedding_deployment: str | None = None

    @model_validator(mode="after")
    def _chosen_providers_have_credentials(self) -> "Settings":
        """Fail at startup, naming every missing variable, not at the first call."""
        needed = []
        if self.llm_provider is LLMProvider.ANTHROPIC:
            needed += ["anthropic_api_key"]
        if self.llm_provider is LLMProvider.AZURE:
            needed += AZURE_CONNECTION + ["azure_openai_chat_deployment"]
        if self.embedding_provider is EmbeddingProvider.AZURE:
            needed += AZURE_CONNECTION + ["azure_openai_embedding_deployment"]

        missing = []
        for name in needed:
            variable = name.upper()  # the field's environment variable
            if not getattr(self, name) and variable not in missing:
                missing.append(variable)
        if missing:
            raise ValueError(f"missing settings: {', '.join(missing)}")
        return self


def build_llm(settings: Settings) -> Model:
    match settings.llm_provider:
        case LLMProvider.OFFLINE:
            return offline_model()
        case LLMProvider.ANTHROPIC:
            provider = AnthropicProvider(
                api_key=settings.anthropic_api_key.get_secret_value()
            )
            return AnthropicModel(settings.anthropic_model, provider=provider)
        case LLMProvider.AZURE:
            provider = AzureProvider(
                api_key=settings.azure_openai_api_key.get_secret_value(),
                azure_endpoint=settings.azure_openai_endpoint,
                api_version=settings.azure_openai_api_version,
            )
            return OpenAIChatModel(
                settings.azure_openai_chat_deployment, provider=provider
            )


class Model2VecEmbedder:
    """A small static embedding model that runs on the CPU with numpy only.

    The model is downloaded on first use into the Hugging Face cache.
    """

    def __init__(self, model_id: str) -> None:
        self.name = model_id
        self._model = StaticModel.from_pretrained(model_id)

    def embed(self, texts: list[str]) -> np.ndarray:
        return _unit_rows(self._model.encode(texts))


class AzureEmbedder:
    """An embedding model deployed on Azure OpenAI.

    On Azure the "model" of a request is the deployment name, which the
    team that runs the Azure resource chooses.
    """

    def __init__(self, client: AzureOpenAI, deployment: str) -> None:
        self.name = f"azure:{deployment}"
        self._client = client
        self._deployment = deployment

    def embed(self, texts: list[str]) -> np.ndarray:
        response = self._client.embeddings.create(model=self._deployment, input=texts)
        # Each returned row says which text it belongs to; sort by it.
        rows = sorted(response.data, key=lambda row: row.index)
        return _unit_rows(np.array([row.embedding for row in rows]))


def build_embedder(settings: Settings) -> Embedder:
    match settings.embedding_provider:
        case EmbeddingProvider.LOCAL:
            return Model2VecEmbedder(settings.local_embedding_model)
        case EmbeddingProvider.AZURE:
            client = AzureOpenAI(
                api_key=settings.azure_openai_api_key.get_secret_value(),
                azure_endpoint=settings.azure_openai_endpoint,
                api_version=settings.azure_openai_api_version,
            )
            return AzureEmbedder(client, settings.azure_openai_embedding_deployment)


def _unit_rows(vectors: np.ndarray) -> np.ndarray:
    """Scale each row to length 1, so a dot product is the cosine similarity."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)
