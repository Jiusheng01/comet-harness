from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI

from app.core.harness.runtime.contracts import (
    HarnessMessage,
    ModelStreamEvent,
    ModelTurn,
    ModelUsage,
    ToolCall,
)


class LangChainModelAdapter:
    """把 LangChain ChatOpenAI 适配为 Harness ModelAdapter。

    Harness Runtime 只认识 HarnessMessage / ModelTurn，
    LangChain 的 Message、tool_calls、usage_metadata 都在这里转换。
    """

    def __init__(self, model: ChatOpenAI) -> None:
        self._model = model

    @property
    def model_name(self) -> str:
        return (
            getattr(self._model, "model_name", None)
            or getattr(self._model, "model", None)
            or "chat"
        )

    async def stream(
        self,
        messages: list[HarnessMessage],
        tools: list[Any],
    ) -> AsyncIterator[ModelStreamEvent]:
        lc_messages = [_to_langchain_message(message) for message in messages]

        model = self._model.bind_tools(tools) if tools else self._model

        gathered = None

        async for chunk in model.astream(lc_messages):
            if chunk.content:
                text = (
                    chunk.content
                    if isinstance(chunk.content, str)
                    else str(chunk.content)
                )

                yield ModelStreamEvent(
                    type="token",
                    text=text,
                )

            gathered = chunk if gathered is None else gathered + chunk

        if gathered is None:
            yield ModelStreamEvent(
                type="completed",
                turn=ModelTurn(),
            )
            return

        raw_tool_calls = getattr(gathered, "tool_calls", None) or []

        tool_calls = [
            ToolCall(
                id=str(call.get("id") or call.get("name") or ""),
                name=str(call.get("name") or ""),
                arguments=call.get("args", {}) or {},
            )
            for call in raw_tool_calls
        ]

        content = getattr(gathered, "content", "") or ""
        text = content if isinstance(content, str) else str(content)

        usage_metadata = getattr(gathered, "usage_metadata", None) or {}

        usage = ModelUsage(
            input_tokens=int(usage_metadata.get("input_tokens", 0) or 0),
            output_tokens=int(usage_metadata.get("output_tokens", 0) or 0),
            cached_tokens=int(
                (usage_metadata.get("input_token_details") or {}).get(
                    "cache_read",
                    0,
                )
                or 0
            ),
        )

        yield ModelStreamEvent(
            type="completed",
            turn=ModelTurn(
                text=text,
                tool_calls=tool_calls,
                usage=usage,
            ),
        )


def _to_langchain_message(message: HarnessMessage) -> BaseMessage:
    """HarnessMessage -> LangChain Message。"""

    if message.role == "system":
        return SystemMessage(content=message.content)

    if message.role == "user":
        return HumanMessage(content=message.content)

    if message.role == "tool":
        return ToolMessage(
            content=message.content,
            tool_call_id=message.tool_call_id or "",
        )

    if message.role == "assistant":
        tool_calls = [
            {
                "id": call.id,
                "name": call.name,
                "args": call.arguments,
                "type": "tool_call",
            }
            for call in message.tool_calls
        ]

        return AIMessage(
            content=message.content,
            tool_calls=tool_calls,
        )

    raise ValueError(f"Unsupported message role: {message.role}")

def from_langchain_messages(
    messages: list[BaseMessage],
) -> list[HarnessMessage]:
    """把现有 LangChain 消息历史转换成 Harness 内部消息。"""

    return [_from_langchain_message(message) for message in messages]


def _from_langchain_message(message: BaseMessage) -> HarnessMessage:
    content = getattr(message, "content", "") or ""
    text = content if isinstance(content, str) else str(content)

    if isinstance(message, SystemMessage):
        return HarnessMessage(
            role="system",
            content=text,
        )

    if isinstance(message, HumanMessage):
        return HarnessMessage(
            role="user",
            content=text,
        )

    if isinstance(message, ToolMessage):
        return HarnessMessage(
            role="tool",
            content=text,
            tool_call_id=str(
                getattr(message, "tool_call_id", "") or ""
            ),
        )

    if isinstance(message, AIMessage):
        raw_tool_calls = getattr(message, "tool_calls", None) or []

        tool_calls = [
            ToolCall(
                id=str(call.get("id") or call.get("name") or ""),
                name=str(call.get("name") or ""),
                arguments=call.get("args", {}) or {},
            )
            for call in raw_tool_calls
        ]

        return HarnessMessage(
            role="assistant",
            content=text,
            tool_calls=tool_calls,
        )

    raise ValueError(
        f"Unsupported LangChain message: {type(message).__name__}"
    )