"""Stand-ins for external models, for unit tests only.

They replace the embedding model or the language model, not our code: the
vector store and the agents under test are real.
"""

import inspect
import re
import zlib

import numpy as np
from pydantic_ai.models.function import FunctionModel

from rag_system.offline_model import offline_model


class WordHashEmbedder:
    """Deterministic bag-of-words vectors: texts that share words are close."""

    name = "test:word-hash-64"

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), 64))
        for row, text in enumerate(texts):
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                vectors[row, zlib.crc32(word.encode()) % 64] += 1.0
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.where(norms == 0, 1, norms)


class BlindEmbedder:
    """Gives every text the same vector: the embedding side sees no difference."""

    name = "test:blind"

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.ones((len(texts), 4)) / 2.0


def offline_except(**scripts) -> FunctionModel:
    """Stands in for a real model: the offline templates, except the roles
    given here (by output name), which run the given function instead."""
    offline = offline_model().function

    async def model(messages, info):
        name = info.output_tools[0].name if info.output_tools else "text"
        if name not in scripts:
            return offline(messages, info)
        response = scripts[name](messages, info)
        if inspect.isawaitable(response):  # a role that takes time
            response = await response
        return response

    return FunctionModel(model)
