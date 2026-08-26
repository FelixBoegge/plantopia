"""Watching a chat reply being produced.

Chat has the diagnosis problem in miniature. A message that consults the corpus and then
the web is silent for several seconds, and silence reads as a failure.

**The reply is produced by ``ChatService.send`` unchanged.** This module watches; it does
not drive. Two things follow, and both are the reason it is arranged this way:

- The transcript a streamed message leaves behind is identical to a single-request one,
  because it is written by the same code rather than by a parallel implementation that has
  to be kept in step.
- A client that disconnects mid-reply still gets its reply recorded. ``send`` runs to
  completion on its own thread whatever the connection does, which is what makes a dropped
  tunnel cost somebody a view of the answer rather than the answer.
"""

import logging
from queue import Empty, Full, Queue
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from runs import steps

logger = logging.getLogger(__name__)

# Generous relative to a chat turn's handful of events. Falling behind this far means a
# reader that has stopped reading, not one that is merely slow.
BACKLOG = 128

# What each tool is called when a person is told about it. The tools' own names are
# internal — `web_search_plant_info` is a function, not something to show anybody.
TOOL_NAMES = {
    "search_plant_knowledge": "the disorder reference",
    "lookup_plant_care_profile": "care guidance for this species",
    "get_local_weather": "the local weather",
    "web_search_plant_info": "the web",
    "get_plant_journal": "this plant's history",
    "suggest_new_diagnosis": "whether this needs a fresh diagnosis",
}


def described(tool: str) -> str:
    """How a lookup is announced.

    An unknown tool is announced without naming itself, on the same reasoning as an
    unmapped graph node: the fallback would leak the internal name exactly when somebody
    had added a tool and forgotten this table.
    """
    return TOOL_NAMES.get(tool, "another source")


class ChatEvents(BaseCallbackHandler):
    """Collects what the agent does, as it does it.

    A queue rather than direct delivery: the agent runs on a worker thread and the reader
    is an event loop, and the reader going away must not be able to disturb the agent.
    """

    def __init__(self) -> None:
        self._events: Queue = Queue(maxsize=BACKLOG)

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        name = (serialized or {}).get("name") or kwargs.get("name") or ""
        self._offer((steps.TOOL, {"source": described(name)}))

    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """Text as it is produced, when the provider streams it.

        Providers that do not stream produce one token here — the whole message — which is
        why the reply is also delivered whole at the end rather than assembled from these.
        """
        if token:
            self._offer((steps.DELTA, {"text": token}))

    def finish(self) -> None:
        """No more events. Wakes a reader waiting on the next one."""
        self._offer(None)

    def next(self, timeout: float):
        """The next event, or ``None`` for both "nothing yet" and "nothing ever again".

        The caller distinguishes them the same way the run stream does: by knowing whether
        the work has finished.
        """
        try:
            return self._events.get(timeout=timeout)
        except Empty:
            return None

    def _offer(self, item) -> None:
        try:
            self._events.put_nowait(item)
        except Full:
            logger.warning("dropped a chat event: the client is not keeping up")
