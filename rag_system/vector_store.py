"""How are chunks stored, filtered and ranked by similarity?

Input: the chunks made by ingestion.chunk_document.

    add(chunks)
        each chunk's text --> embedder --> a vector of numbers (length 1)
        each chunk's text --> its words --> BM25 word statistics

    search(query, domain, clearance, limit, include_superseded=False,
           ranking=Ranking.HYBRID)
        1. candidates: the chunks of `domain` (every domain if None) that
           `clearance` may read, without superseded versions unless asked for
           (a document is superseded when another one names it in
           `supersedes`)
        2. two rankings of the candidates:
             by meaning: cosine similarity of the query vector and each
                         chunk vector
             by words:   BM25 score of the query's words in each chunk
        3. reciprocal rank fusion (RRF) merges the two rankings
           (with ranking=Ranking.EMBEDDING: the ranking by meaning alone;
           the classifier uses it, the domain agents use hybrid)
        4. the `limit` best candidates, each with its cosine similarity
                                                        --> [Hit, Hit, ...]

The filters run before the ranking, so a chunk the caller may not read
never reaches an agent or a model, and a rule that no longer applies does
not take a place in the results. Superseded versions stay in the index for
questions about history ("how many approvers were needed in 2025?").
Adding a new version is the whole knowledge update: from that moment the
old version is history.

`VectorStore` is the interface the agents depend on; `InMemoryVectorStore`
is the demo's implementation (numpy and BM25 in memory, rebuilt at every
start). A production store on PostgreSQL with pgvector would be another
class with the same three members.
"""

import re
from enum import StrEnum
from typing import Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict
from rank_bm25 import BM25Okapi

from rag_system.ingestion import Chunk
from rag_system.messages import Clearance, Domain

# Reciprocal rank fusion gives each chunk 1 / (RRF_K + rank) from each
# ranking and adds them up. A chunk ranked first by words and tenth by
# meaning gets 1/60 + 1/70 = 0.0310; a chunk ranked fifth by both gets
# 1/65 + 1/65 = 0.0308. 60 is the constant of the paper that introduced
# the method (Cormack, Clarke and Buettcher, 2009); it keeps the first few
# ranks from dominating.
RRF_K = 60


class Ranking(StrEnum):
    """How search orders the candidates."""

    HYBRID = "hybrid"  # meaning and words, merged with RRF
    EMBEDDING = "embedding"  # meaning only: cosine similarity


class Embedder(Protocol):
    """Any embedding model: local (model2vec) or remote (Azure OpenAI)."""

    name: str  # e.g. "minishlab/potion-base-8M"

    def embed(self, texts: list[str]) -> np.ndarray:
        """One row of numbers per text, each row of length 1."""
        ...


class Hit(BaseModel):
    """One chunk found by a search, with its cosine similarity to the query."""

    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    similarity: float  # 1 = same direction, 0 = unrelated


class VectorStore(Protocol):
    """What the agents need from a store, whatever the store is."""

    @property
    def model(self) -> str:
        """The embedding model that built the index."""
        ...

    def add(self, chunks: list[Chunk]) -> None: ...

    def search(
        self,
        query: str,
        domain: Domain | None,
        clearance: Clearance,
        limit: int,
        include_superseded: bool = False,
        ranking: Ranking = Ranking.HYBRID,
    ) -> list[Hit]:
        """`domain=None` searches every domain (the classifier does this)."""
        ...


class InMemoryVectorStore:
    """The demo's store: vectors in a numpy table, BM25 statistics in memory."""

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self._chunks: list[Chunk] = []
        self._vectors = np.zeros((0, 0))  # one row per chunk
        self._bm25: BM25Okapi | None = None
        self._superseded: set[str] = set()  # ids named in some `supersedes`

    @property
    def model(self) -> str:
        return self._embedder.name

    def add(self, chunks: list[Chunk]) -> None:
        """Add chunks to the index; also used for knowledge updates."""
        if not chunks:
            return
        new_vectors = self._embedder.embed([chunk.text for chunk in chunks])
        if self._chunks:
            self._vectors = np.vstack([self._vectors, new_vectors])
        else:
            self._vectors = new_vectors
        self._chunks.extend(chunks)
        for chunk in chunks:
            if chunk.document.supersedes:
                self._superseded.add(chunk.document.supersedes)
        # BM25 needs word statistics over all chunks, so it is rebuilt.
        self._bm25 = BM25Okapi([_words(chunk.text) for chunk in self._chunks])

    def search(
        self,
        query: str,
        domain: Domain | None,
        clearance: Clearance,
        limit: int,
        include_superseded: bool = False,
        ranking: Ranking = Ranking.HYBRID,
    ) -> list[Hit]:
        # 1. The candidates: chunks of the domain that the caller may read.
        candidates = self._readable_candidates(domain, clearance, include_superseded)
        if not candidates or not _words(query):
            return []

        # 2. Two rankings of the candidates.
        similarity = self._cosine_similarity(query)
        rank_by_meaning = _rank(candidates, similarity)
        word_scores = self._bm25.get_scores(_words(query))
        rank_by_words = _rank(candidates, word_scores)

        # 3. Merge the two rankings, or keep the one by meaning.
        if ranking is Ranking.HYBRID:
            score = _fuse_rankings(candidates, rank_by_meaning, rank_by_words)
        else:
            score = {index: float(similarity[index]) for index in candidates}

        # 4. The best `limit` candidates, with their cosine similarity.
        best_first = sorted(candidates, key=score.get, reverse=True)
        hits = []
        for index in best_first[:limit]:
            hits.append(
                Hit(chunk=self._chunks[index], similarity=float(similarity[index]))
            )
        return hits

    def _readable_candidates(
        self, domain: Domain | None, clearance: Clearance, include_superseded: bool
    ) -> list[int]:
        """Positions of the chunks of `domain` (or all) that `clearance` may read."""
        candidates = []
        for index, chunk in enumerate(self._chunks):
            in_domain = domain is None or chunk.document.domain is domain
            allowed = clearance.allows(chunk.document.classification)
            in_force = chunk.document.id not in self._superseded
            if in_domain and allowed and (in_force or include_superseded):
                candidates.append(index)
        return candidates

    def _cosine_similarity(self, query: str) -> np.ndarray:
        """The cosine similarity of the query to every chunk, one number each.

        Every vector has length 1, so the cosine is the dot product: the sum
        of the products of the two vectors' numbers, position by position.
        A matrix product (`@`) computes it for all chunks at once:
        (chunks x 256 numbers) @ (256 numbers) = one number per chunk.
        """
        query_vector = self._embedder.embed([query])[0]
        return self._vectors @ query_vector


def _rank(candidates: list[int], scores: np.ndarray) -> dict[int, int]:
    """Each candidate's rank: how many candidates score strictly higher.

    Equal scores get the same rank. Otherwise a ranking that cannot tell
    chunks apart would still hand out ranks 0, 1, 2 by insertion order and
    give the first chunk an advantage it did not earn.
    """
    rank = {}
    for index in candidates:
        higher = 0
        for other in candidates:
            if scores[other] > scores[index]:
                higher += 1
        rank[index] = higher
    return rank


def _fuse_rankings(
    candidates: list[int], first: dict[int, int], second: dict[int, int]
) -> dict[int, float]:
    """Reciprocal rank fusion of two rankings (see RRF_K)."""
    fused = {}
    for index in candidates:
        fused[index] = 1 / (RRF_K + first[index]) + 1 / (RRF_K + second[index])
    return fused


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())
