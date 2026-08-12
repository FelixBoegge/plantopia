"""Orchestration for the plant-scoped chat page."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from langgraph.checkpoint.base import BaseCheckpointSaver

from agent.chat_agent import make_chat_agent
from agent.deps import Deps
from data.db import transaction
from data.repositories.messages import MessageRecord, MessageRepository


@dataclass(frozen=True, slots=True)
class ChatTurn:
    """One exchange: the agent's reply, and whether it escalated to a new diagnosis."""

    reply: str
    escalated: bool


class ChatService:
    """Drives the chat agent on behalf of the UI, persisting the transcript.

    A fresh agent is built per ``send`` call rather than cached per plant: the
    system prompt bakes in the plant's latest diagnosis, and caching it would let
    that go stale the moment a re-check completes between messages. Conversation
    memory survives that rebuild because it lives in the checkpointer, keyed by
    thread id, not in the agent object.
    """

    def __init__(
        self,
        *,
        deps: Deps,
        messages: MessageRepository,
        checkpointer: BaseCheckpointSaver,
        now: Callable[[], datetime],
    ) -> None:
        self._deps = deps
        self._messages = messages
        self._checkpointer = checkpointer
        self._now = now

    @staticmethod
    def _thread_id(plant_id: int) -> str:
        """The ReAct loop's own scratch thread, distinct from any diagnosis thread
        for the same plant (design spec §5)."""
        return f"chat:{plant_id}"

    def history(self, plant_id: int) -> list[MessageRecord]:
        return self._messages.list_for_plant(plant_id)

    def send(self, plant_id: int, content: str) -> ChatTurn:
        """Record the user's message, run the agent, record and return its reply.

        The user's message and the assistant's reply are committed in separate
        transactions rather than one spanning the agent invocation: the user's
        message should stay durable even if the agent call itself fails partway
        through.
        """
        with transaction(self._messages.connection):
            self._messages.create(
                plant_id=plant_id, role="user", content=content, tool_calls=None, now=self._now()
            )

        agent, escalation = make_chat_agent(self._deps, plant_id, self._checkpointer)
        config = {"configurable": {"thread_id": self._thread_id(plant_id)}}
        result = agent.invoke({"messages": [{"role": "user", "content": content}]}, config)
        reply = result["messages"][-1].content

        with transaction(self._messages.connection):
            self._messages.create(
                plant_id=plant_id, role="assistant", content=reply, tool_calls=None, now=self._now()
            )
        return ChatTurn(reply=reply, escalated=bool(escalation))
