"""Tests for multimodal embedding. All HTTP is mocked at the transport layer."""

import httpx
import respx

from core.embeddings import EMBEDDINGS_URL, ImageEmbedder

_OK = {"data": [{"embedding": [0.1, 0.2, 0.3], "index": 0}]}


def _embedder() -> ImageEmbedder:
    return ImageEmbedder(
        api_key="sk-test",
        base_url="https://openrouter.ai/api/v1",
        model="google/gemini-embedding-2",
    )


@respx.mock
def test_returns_the_embedding_vector():
    respx.post(EMBEDDINGS_URL).mock(return_value=httpx.Response(200, json=_OK))
    assert _embedder().embed_image(b"hi", "image/png") == [0.1, 0.2, 0.3]


@respx.mock
def test_sends_the_image_as_a_data_url_in_a_content_array():
    route = respx.post(EMBEDDINGS_URL).mock(return_value=httpx.Response(200, json=_OK))
    _embedder().embed_image(b"hi", "image/png")

    body = route.calls[0].request.read().decode()
    assert "data:image/png;base64,aGk=" in body
    assert "image_url" in body


@respx.mock
def test_sends_the_configured_model():
    route = respx.post(EMBEDDINGS_URL).mock(return_value=httpx.Response(200, json=_OK))
    _embedder().embed_image(b"hi", "image/png")
    assert "google/gemini-embedding-2" in route.calls[0].request.read().decode()


@respx.mock
def test_authorises_with_the_api_key():
    route = respx.post(EMBEDDINGS_URL).mock(return_value=httpx.Response(200, json=_OK))
    _embedder().embed_image(b"hi", "image/png")
    assert route.calls[0].request.headers["authorization"] == "Bearer sk-test"


@respx.mock
def test_a_server_error_returns_none_rather_than_raising():
    """The image path is additive — losing it must never fail a diagnosis."""
    respx.post(EMBEDDINGS_URL).mock(return_value=httpx.Response(500))
    assert _embedder().embed_image(b"hi", "image/png") is None


@respx.mock
def test_a_timeout_returns_none():
    respx.post(EMBEDDINGS_URL).mock(side_effect=httpx.TimeoutException("slow"))
    assert _embedder().embed_image(b"hi", "image/png") is None


@respx.mock
def test_a_malformed_payload_returns_none():
    respx.post(EMBEDDINGS_URL).mock(return_value=httpx.Response(200, json={"data": []}))
    assert _embedder().embed_image(b"hi", "image/png") is None


@respx.mock
def test_a_model_that_rejects_images_returns_none():
    """Not every embedding model is multimodal; degrade rather than crash."""
    respx.post(EMBEDDINGS_URL).mock(
        return_value=httpx.Response(400, json={"error": {"message": "image input unsupported"}})
    )
    assert _embedder().embed_image(b"hi", "image/png") is None


def test_empty_image_data_returns_none_without_a_request():
    with respx.mock:
        assert _embedder().embed_image(b"", "image/png") is None


@respx.mock
def test_a_non_list_data_payload_returns_none():
    respx.post(EMBEDDINGS_URL).mock(return_value=httpx.Response(200, json={"data": "unexpected"}))
    assert _embedder().embed_image(b"hi", "image/png") is None


@respx.mock
def test_a_non_dict_data_item_returns_none():
    respx.post(EMBEDDINGS_URL).mock(return_value=httpx.Response(200, json={"data": ["oops"]}))
    assert _embedder().embed_image(b"hi", "image/png") is None
