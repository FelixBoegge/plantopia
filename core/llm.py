"""Chat-model factory. This module is the seam tests replace — nothing else
constructs a model directly.

Every model call is routed through OpenRouter, which exposes an OpenAI-compatible
chat-completions API, so ``ChatOpenAI`` works unchanged with a different base URL.
The benefit is that swapping between providers is a configuration change rather than
a code change.

Three tiers exist because the pipeline's jobs differ enormously in difficulty, and on
OpenRouter the price difference between tiers is often more than tenfold.
"""

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from core.config import get_settings


def build_chat_model(
    *,
    model: str | None = None,
    temperature: float | None = None,
) -> BaseChatModel:
    """Return a chat model pointed at OpenRouter.

    Args:
        model: Model slug, for example ``"google/gemini-2.5-flash"``. Defaults to the
            configured reasoning tier.
        temperature: Override the configured default temperature.
    """
    settings = get_settings()
    return ChatOpenAI(
        model=model or settings.reasoning_model,
        temperature=settings.default_temperature if temperature is None else temperature,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        default_headers={
            "HTTP-Referer": settings.app_url,
            "X-Title": settings.app_title,
        },
        # OpenRouter load-balances a model across several upstream providers, and they
        # do not all support the same parameters. Without this, a request can land on
        # a provider that ignores tool calling, and every structured output in the
        # pipeline fails intermittently and unreproducibly. This restricts routing to
        # providers that honour the parameters we send.
        extra_body={"provider": {"require_parameters": True}},
    )


def build_reasoning_model(*, temperature: float | None = None) -> BaseChatModel:
    """Text reasoning: question selection, diagnosis, treatment planning."""
    return build_chat_model(model=get_settings().reasoning_model, temperature=temperature)


def build_vision_model(*, temperature: float | None = None) -> BaseChatModel:
    """Species identification and symptom extraction. Needs real visual acuity."""
    return build_chat_model(model=get_settings().vision_model, temperature=temperature)


def build_gate_model(*, temperature: float | None = None) -> BaseChatModel:
    """The two binary image checks.

    ``guard_input`` and ``quality_check`` ask yes-or-no questions about an image and
    run on every single diagnosis. A cheap model is entirely adequate and this is
    where most of the per-diagnosis cost would otherwise go.
    """
    return build_chat_model(model=get_settings().gate_model, temperature=temperature)


def build_embeddings() -> Embeddings:
    """Return the text embeddings client for corpus indexing and text queries.

    OpenRouter exposes an OpenAI-compatible ``/embeddings`` endpoint, so the same key
    and base URL serve embeddings as well as chat.

    ``check_embedding_ctx_length=False`` matters: LangChain otherwise tries to
    tokenise inputs with tiktoken keyed on the model name in order to chunk them, and
    a provider-prefixed OpenRouter slug like ``openai/text-embedding-3-small`` is not a
    name tiktoken recognises. Disabling it sends the text through unmodified, which is
    what we want — corpus sections are well under any context limit.

    For embedding *images* see ``core.embeddings.ImageEmbedder``: LangChain's
    embeddings interface is text-only, so the multimodal call is made directly.
    """
    settings = get_settings()
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        check_embedding_ctx_length=False,
    )
