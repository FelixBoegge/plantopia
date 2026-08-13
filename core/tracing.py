"""Optional LangSmith tracing.

Enabled by configuration alone. LangChain's tracer reads process environment
variables, so this module sets them rather than threading a callback through the
graph — which is the property ``PLAN.md`` §15 chose LangSmith for: every graph
node, tool call, retrieval and model call appears in a trace with no wiring.

Absent a key this is a no-op, following the ``tavily_api_key`` precedent so that a
fresh clone runs without a LangSmith account.
"""

import logging
import os

from core.config import Settings

logger = logging.getLogger(__name__)


def configure_tracing(settings: Settings) -> bool:
    """Enable LangSmith tracing when a key is configured.

    Returns:
        ``True`` when tracing was enabled, ``False`` when no usable key was present.
    """
    key = (settings.langsmith_api_key or "").strip()
    if not key:
        logger.info("LangSmith tracing disabled: no API key configured")
        return False

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    logger.info("LangSmith tracing enabled, project %r", settings.langsmith_project)
    return True
