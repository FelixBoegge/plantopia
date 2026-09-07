"""Deterministic offline embeddings.

Hashes tokens into a fixed-dimension vector and L2-normalises. Cosine similarity
between two such vectors reflects real word overlap, so retrieval ranking tests
are meaningful without touching a network.
"""

import math
import re
import zlib
from typing import ClassVar

from langchain_core.embeddings import Embeddings

from data.models import EMBEDDING_DIMENSIONS

_TOKEN_RE = re.compile(r"[a-z]+")


class HashingEmbeddings(Embeddings):
    """Bag-of-words hashing embeddings for tests.

    Implements the LangChain text-embeddings interface (``embed_documents`` and
    ``embed_query``). It served an ``embed_image`` protocol too, until the cross-modal
    path was removed for want of any reachable model that could supply it (``U2``).
    """

    # The corpus column's width, not an arbitrary one. `corpus_chunks.embedding` is
    # `vector(1536)` and cannot store anything narrower, so a fake that produced its own
    # width could not be written to the table the retriever reads. The extra dimensions
    # are zeros for every token that does not hash into them, and zeros change no dot
    # product and no norm — so cosine similarity is the same geometry either way.
    dimensions: ClassVar[int] = EMBEDDING_DIMENSIONS

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _TOKEN_RE.findall(text.lower()):
            vector[zlib.crc32(token.encode()) % self.dimensions] += 1.0

        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0.0:
            return vector
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)
