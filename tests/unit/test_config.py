"""Settings choose the models; the factories build them; bad settings fail at once."""

import httpx2
import numpy as np
import pytest
from openai import AzureOpenAI
from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent, ToolOutput

from rag_system.config import (
    AzureEmbedder,
    EmbeddingProvider,
    LLMProvider,
    Settings,
    build_embedder,
    build_llm,
)
from rag_system.offline_model import OfflineModelError


def settings_from(**values) -> Settings:
    """Settings from the given values only: no .env file is read."""
    return Settings(_env_file=None, **values)


def test_with_no_settings_the_system_runs_offline_with_local_embeddings():
    settings = settings_from()

    assert settings.llm_provider is LLMProvider.OFFLINE
    assert settings.embedding_provider is EmbeddingProvider.LOCAL


def test_anthropic_without_a_key_fails_at_startup_and_names_the_variable():
    with pytest.raises(ValidationError, match="ANTHROPIC_API_KEY"):
        settings_from(llm_provider="anthropic", anthropic_api_key=None)


def test_azure_llm_without_settings_names_every_missing_variable_at_once():
    with pytest.raises(ValidationError) as error:
        settings_from(llm_provider="azure")

    for variable in [
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_VERSION",
        "AZURE_OPENAI_CHAT_DEPLOYMENT",
    ]:
        assert variable in str(error.value)


def test_azure_embeddings_need_the_embedding_deployment_not_the_chat_one():
    azure = {
        "azure_openai_api_key": "key",
        "azure_openai_endpoint": "https://example.openai.azure.com",
        "azure_openai_api_version": "2024-10-21",
    }

    with pytest.raises(ValidationError) as error:
        settings_from(embedding_provider="azure", **azure)

    assert "AZURE_OPENAI_EMBEDDING_DEPLOYMENT" in str(error.value)
    assert "AZURE_OPENAI_CHAT_DEPLOYMENT" not in str(error.value)


def test_the_local_embedder_gives_one_row_of_length_1_per_text_and_its_name():
    embedder = build_embedder(settings_from())

    vectors = embedder.embed(["deploy a microservice", "data retention rules"])

    assert embedder.name == "minishlab/potion-base-8M"
    assert vectors.shape == (2, 256)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0)


def test_the_azure_embedder_asks_its_deployment_and_keeps_the_order_of_the_texts():
    requests = []

    def azure(request: httpx2.Request) -> httpx2.Response:
        """Stands in for the Azure OpenAI service; answers in reverse order."""
        requests.append(request)
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "model": "text-embedding-3-small",
                "data": [
                    {"object": "embedding", "index": 1, "embedding": [0.0, 2.0]},
                    {"object": "embedding", "index": 0, "embedding": [3.0, 0.0]},
                ],
                "usage": {"prompt_tokens": 4, "total_tokens": 4},
            },
        )

    client = AzureOpenAI(
        api_key="key",
        azure_endpoint="https://example.openai.azure.com",
        api_version="2024-10-21",
        http_client=httpx2.Client(transport=httpx2.MockTransport(azure)),
    )
    embedder = AzureEmbedder(client, deployment="embeddings-prod")

    vectors = embedder.embed(["first text", "second text"])

    assert "/deployments/embeddings-prod/embeddings" in str(requests[0].url)
    assert embedder.name == "azure:embeddings-prod"
    assert np.allclose(vectors, [[1.0, 0.0], [0.0, 1.0]])


AZURE = {
    "azure_openai_api_key": "key",
    "azure_openai_endpoint": "https://example.openai.azure.com",
    "azure_openai_api_version": "2024-10-21",
    "azure_openai_chat_deployment": "chat-prod",
    "azure_openai_embedding_deployment": "embeddings-prod",
}


def test_azure_embedding_settings_build_an_embedder_named_after_the_deployment():
    embedder = build_embedder(settings_from(embedding_provider="azure", **AZURE))

    assert embedder.name == "azure:embeddings-prod"


def test_anthropic_settings_build_the_chosen_claude_model():
    settings = settings_from(
        llm_provider="anthropic",
        anthropic_api_key="key",
        anthropic_model="claude-haiku-5-5",
    )

    assert build_llm(settings).model_name == "claude-haiku-5-5"


def test_azure_settings_build_a_chat_model_that_calls_the_deployment():
    model = build_llm(settings_from(llm_provider="azure", **AZURE))

    assert model.model_name == "chat-prod"
    assert model.system == "azure"


def test_offline_settings_build_a_stand_in_model_that_needs_no_key():
    model = build_llm(settings_from())

    assert model.model_name == "offline"


async def test_the_offline_model_refuses_a_request_it_has_no_template_for():
    class Weather(BaseModel):
        forecast: str

    agent = Agent(
        build_llm(settings_from()), output_type=ToolOutput(Weather, name="weather")
    )

    with pytest.raises(OfflineModelError, match="weather"):
        await agent.run("Will it rain tomorrow?")
