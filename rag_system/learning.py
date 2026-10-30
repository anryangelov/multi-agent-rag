"""How does feedback change what the agents retrieve next time?

    a person rates each source of an answer to a question
                                           --> Rating(chunk_id, useful)
    ChunkWeights.apply(question, ratings)
        keeps each rating with the question it was given for
    a new question arrives: ChunkWeights.for_question(question)
        a rating counts only if the new question is close in meaning to
        the rated one (cosine >= 0.6); each counting rating multiplies the
        chunk's weight by 1.25 (useful) or 0.8 (not useful); a weight
        stays between 0.5 and 2
    the DomainAgent's search
        orders its hits by (position + 1) / weight; keeps the first eight,
        except a chunk with a weight below 1, and any other chunk while
        similarity x weight >= 0.4

A chunk can be useful for one question and beside the point for another
(TEC-6#5, "log retention follows CMP-3", answers a question about logs,
not one about slow APIs). Tying each rating to its question keeps what one
question taught from changing unrelated questions; FLAIR (arXiv
2508.13390) stores feedback the same way. Weights change what is
retrieved, never which side of a conflict wins (conflicts.py).

SimulatedUser stands in for people in the demo and the evals: a source is
useful when its document is an expected answer in the gold set, and the
user is wrong a set share of the time, as real people are.
"""

import random

import numpy as np
from pydantic import BaseModel, ConfigDict

from rag_system.messages import FinalAnswer
from rag_system.vector_store import Embedder

UP = 1.25  # factor for a useful rating
DOWN = 0.8  # factor for a rating "not useful"
LOWEST, HIGHEST = 0.5, 2.0
SIMILAR_QUESTION = 0.6  # cosine from which a rating carries over


class Rating(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: str  # e.g. "TEC-3#5"
    useful: bool


class RatedSource(BaseModel):
    """One rating as it is kept: the question it was given for, and when."""

    model_config = ConfigDict(frozen=True)

    question: str
    chunk_id: str
    useful: bool


class QuestionWeights:
    """The weights that apply to one question."""

    def __init__(self, factors: dict[str, float]) -> None:
        self._factors = factors

    def weight(self, chunk_id: str) -> float:
        factor = self._factors.get(chunk_id, 1.0)
        return min(HIGHEST, max(LOWEST, factor))


class ChunkWeights:
    """What feedback has taught, kept per rated question."""

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self.history: list[RatedSource] = []
        self._vectors: list[np.ndarray] = []  # one per rating, as history

    def apply(self, question: str, ratings: list[Rating]) -> None:
        if not ratings:
            return
        vector = self._embedder.embed([question])[0]
        for rating in ratings:
            self.history.append(
                RatedSource(
                    question=question, chunk_id=rating.chunk_id, useful=rating.useful
                )
            )
            self._vectors.append(vector)

    def for_question(self, question: str) -> QuestionWeights:
        """The product of the factors of the ratings given for questions
        close to this one."""
        factors: dict[str, float] = {}
        if self.history:
            vector = self._embedder.embed([question])[0]
            closeness = np.array(self._vectors) @ vector
            for record, cosine in zip(self.history, closeness, strict=True):
                if cosine >= SIMILAR_QUESTION:
                    factor = UP if record.useful else DOWN
                    factors[record.chunk_id] = (
                        factors.get(record.chunk_id, 1.0) * factor
                    )
        return QuestionWeights(factors)

    def reset(self) -> None:
        self.history.clear()
        self._vectors.clear()


class SimulatedUser:
    def __init__(self, rng: random.Random, wrong_share: float = 0.1) -> None:
        self._rng = rng
        self._wrong_share = wrong_share

    def rate(self, answer: FinalAnswer, expected: set[str]) -> list[Rating]:
        """One rating per cited chunk: useful when its document is expected,
        flipped for a `wrong_share` of the ratings."""
        ratings = []
        for source in answer.sources:
            useful = source.doc_id in expected
            if self._rng.random() < self._wrong_share:
                useful = not useful
            ratings.append(Rating(chunk_id=source.chunk_id, useful=useful))
        return ratings
