"""Web-search escalation.

The curated corpus is authoritative and reproducible, so it is consulted first. The
web is current but unvetted, so it is a fallback whose provenance is shown to the
user. ``should_escalate`` is the gate that decides between them.
"""

import logging
from collections.abc import Sequence
from urllib.parse import urlparse

import httpx

from agent.schemas import WEB_DOC_PREFIX, Passage
from core.config import Settings

logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"
_TIMEOUT = httpx.Timeout(15.0)


def should_escalate(
    passages: Sequence[Passage],
    species_confidence: float,
    settings: Settings,
) -> bool:
    """Decide whether local retrieval was good enough.

    Escalates when the corpus produced nothing relevant, or when the species is
    unidentified — in which case the corpus may simply not cover this plant.
    """
    if not passages:
        return True
    if species_confidence < settings.species_confidence_threshold:
        return True
    best_score = max(p.score for p in passages)
    return best_score < settings.retrieval_score_threshold


def web_search_plant_info(
    query: str,
    *,
    api_key: str | None,
    max_results: int = 4,
    client: httpx.Client | None = None,
) -> list[Passage]:
    """Search the web for plant-health information.

    Returns an empty list on any failure, including a missing API key. Web search is
    an enhancement; losing it must never fail a diagnosis.
    """
    if not api_key or not query.strip():
        return []

    owns_client = client is None
    client = client or httpx.Client(timeout=_TIMEOUT)
    try:
        response = client.post(
            TAVILY_URL,
            json={
                "api_key": api_key,
                "query": f"plant health: {query}",
                "max_results": max_results,
                "search_depth": "basic",
            },
        )
        response.raise_for_status()
        results = response.json().get("results") or []
        return [_to_passage(r) for r in results[:max_results]]
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        logger.warning("web search failed for %r", query, exc_info=True)
        return []
    finally:
        if owns_client:
            client.close()


def _to_passage(result: dict) -> Passage:
    host = urlparse(result["url"]).netloc or "unknown"
    return Passage(
        doc_id=f"{WEB_DOC_PREFIX}{host}",
        section=result.get("title") or "Web result",
        text=result.get("content") or "",
        score=max(0.0, min(1.0, float(result.get("score", 0.0)))),
    )
