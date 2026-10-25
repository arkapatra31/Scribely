"""A stand-in chat model: ``with_structured_output(schema).ainvoke(messages)`` calls a handler."""

import asyncio
from collections.abc import Callable
from typing import Any, cast

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

Handler = Callable[[type[BaseModel], str], BaseModel]


class FakeLLM:
    def __init__(self, handler: Handler, delay: float = 0.0) -> None:
        self.handler = handler
        self.delay = delay
        self.calls: list[tuple[str, str]] = []  # (schema name, prompt)
        self.active = 0
        self.max_active = 0

    def with_structured_output(self, schema: type[BaseModel], **_: Any) -> "_Bound":
        return _Bound(self, schema)

    def as_chat_model(self) -> BaseChatModel:
        return cast(BaseChatModel, self)


class _Bound:
    def __init__(self, llm: FakeLLM, schema: type[BaseModel]) -> None:
        self.llm, self.schema = llm, schema

    async def ainvoke(self, messages: list[Any]) -> BaseModel:
        prompt = messages[-1].content
        self.llm.calls.append((self.schema.__name__, prompt))
        self.llm.active += 1
        self.llm.max_active = max(self.llm.max_active, self.llm.active)
        try:
            if self.llm.delay:
                await asyncio.sleep(self.llm.delay)
            return self.llm.handler(self.schema, prompt)
        finally:
            self.llm.active -= 1
