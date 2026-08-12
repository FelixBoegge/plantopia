"""Fake chat models. Unit tests never touch a real model."""

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel


class ScriptedChatModel(BaseChatModel):
    """Returns queued string responses in order. Records every prompt it saw."""

    responses: list[str]
    prompts: list[list[BaseMessage]] = []

    def __init__(self, responses: Sequence[str], **kwargs: Any) -> None:
        super().__init__(responses=list(responses), prompts=[], **kwargs)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        assert self.responses, "script exhausted: the model was called more times than scripted"
        self.prompts.append(messages)
        content = self.responses.pop(0)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])


class ScriptedStructuredModel(BaseChatModel):
    """Its ``with_structured_output`` returns queued Pydantic objects in order.

    This is the fake most node tests use, because nodes request structured output.
    """

    objects: list[BaseModel]
    prompts: list[Any] = []
    call_count: int = 0

    def __init__(self, objects: Sequence[BaseModel], **kwargs: Any) -> None:
        super().__init__(objects=list(objects), prompts=[], call_count=0, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "scripted-structured"

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        raise NotImplementedError("use with_structured_output")

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable:
        def _respond(prompt: Any) -> BaseModel:
            assert self.objects, "script exhausted: more structured calls than scripted objects"
            self.prompts.append(prompt)
            self.call_count += 1
            return self.objects.pop(0)

        return RunnableLambda(_respond)


class ScriptedToolCallingModel(BaseChatModel):
    """For ReAct-style agents (``langchain.agents.create_agent``).

    ``bind_tools`` is a no-op returning ``self`` — ``BaseChatModel``'s default
    raises ``NotImplementedError``, which is fatal the moment a tool-calling agent
    actually runs. Responses are queued ``AIMessage`` objects, which may carry
    ``tool_calls`` to script a multi-step ReAct loop.
    """

    responses: list[AIMessage]

    def __init__(self, responses: Sequence[AIMessage], **kwargs: Any) -> None:
        super().__init__(responses=list(responses), **kwargs)

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-calling"

    def bind_tools(
        self, tools: Any, *, tool_choice: Any = None, **kwargs: Any
    ) -> "ScriptedToolCallingModel":
        return self

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        assert self.responses, "script exhausted: the model was called more times than scripted"
        message = self.responses.pop(0)
        return ChatResult(generations=[ChatGeneration(message=message)])


class FailingChatModel(BaseChatModel):
    """Raises on every call. For testing degradation paths."""

    exc: Exception

    def __init__(self, exc: Exception, **kwargs: Any) -> None:
        super().__init__(exc=exc, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "failing"

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        raise self.exc

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable:
        def _raise(_: Any) -> BaseModel:
            raise self.exc

        return RunnableLambda(_raise)
