"""Structured-output invocation with a single repair retry.

Six nodes ask a model for a validated Pydantic object. When validation fails, the
error is fed back once so the model can correct itself; a second failure is a real
failure and the caller degrades.
"""

import logging
from collections.abc import Sequence
from typing import Any, TypeVar

from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class StructuredOutputFailed(Exception):  # noqa: N818
    """The model could not produce output matching the schema."""


def invoke_structured(  # noqa: UP047
    model: Any,
    schema: type[T],
    messages: Sequence[BaseMessage],
    *,
    retries: int = 1,
    method: str | None = None,
) -> T:
    """Invoke ``model`` for a ``schema``-shaped result.

    Args:
        model: Anything exposing ``with_structured_output``.
        schema: The Pydantic model to validate against.
        messages: The prompt.
        retries: Repair attempts after the first failure.
        method: Passed through to ``with_structured_output``. Leave unset to use
            LangChain's default of tool calling. If you switch to an OpenRouter model
            that does not support tools, pass ``"json_schema"`` — this parameter is
            the escape hatch that makes such a switch a one-line change.

    Raises:
        StructuredOutputFailed: if every attempt fails.
    """
    kwargs = {"method": method} if method else {}
    prompt = list(messages)
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            return model.with_structured_output(schema, **kwargs).invoke(prompt)
        except ValidationError as exc:
            last_error = exc
            logger.warning("structured output failed validation on attempt %d", attempt + 1)
            prompt = [
                *messages,
                HumanMessage(
                    "Your previous response did not match the required schema.\n"
                    f"Validation errors:\n{exc}\n"
                    "Respond again, matching the schema exactly."
                ),
            ]
        except Exception as exc:  # noqa: BLE001 - deliberately broad; caller degrades
            last_error = exc
            logger.warning("structured output call failed on attempt %d", attempt + 1)

    raise StructuredOutputFailed(f"{schema.__name__} could not be produced: {last_error}")
