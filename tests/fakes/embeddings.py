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

_TOKEN_RE = re.compile(r"[a-z]+")


class HashingEmbeddings(Embeddings):
    """Bag-of-words hashing embeddings for tests.

    Serves both the LangChain text-embeddings interface (``embed_documents`` and
    ``embed_query``) and the image-embedder protocol (``embed_image``), so the same
    instance can drive both the text and cross-modal retrieval paths in tests.
    """

    dimensions: ClassVar[int] = 256

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

    def embed_image(self, data: bytes, media_type: str) -> list[float]:
        """Deterministic pseudo-embedding for an image, no real vision involved."""
        return self._embed(f"image {media_type} {data!r}")
