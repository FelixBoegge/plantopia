"""Multimodal embedding.

``google/gemini-embedding-2`` places text and images in one vector space, which lets
a photograph be matched against the text corpus directly (spec §10.4). LangChain's
``Embeddings`` interface accepts strings only, so the image call is made against
OpenRouter's ``/embeddings`` endpoint here.

Every failure returns ``None``. The image path is additive: without it the diagnosis
proceeds on the text path exactly as it would have.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"
_TIMEOUT = httpx.Timeout(20.0)


class ImageEmbedder:
    """Embeds images into the same vector space as the corpus text."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._url = f"{base_url.rstrip('/')}/embeddings"
        self._model = model
        self._client = client

    def embed_image(self, data_b64: str, media_type: str) -> list[float] | None:
        """Return the embedding vector for one image, or None on any failure."""
        if not data_b64:
            return None

        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=_TIMEOUT)
        try:
            response = client.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "input": [
                        {
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{media_type};base64,{data_b64}"},
                                }
                            ]
                        }
                    ],
                },
            )
            response.raise_for_status()
            data = response.json().get("data") or []
            if not data:
                return None
            vector = data[0].get("embedding")
            return list(vector) if vector else None
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            logger.warning("image embedding failed", exc_info=True)
            return None
        finally:
            if owns_client:
                client.close()
