from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

MessageRole = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True)
class HarnessMessage:
    """Harness 内部统一消息格式，不依赖 LangChain Message。"""

    role: MessageRole
    content: str = ""
    tool_call_id: str | None = None
    tool_calls: list["ToolCall"] = field(default_factory=list)


@dataclass(slots=True)
class ToolCall:
    """模型产生的统一工具调用描述。"""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ModelUsage:
    """统一模型 token 使用信息。"""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


@dataclass(slots=True)
class ModelTurn:
    """模型完成一轮推理后的标准结果。"""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: ModelUsage = field(default_factory=ModelUsage)


@dataclass(slots=True)
class ModelStreamEvent:
    """ModelAdapter 向 Runtime 输出的流式事件。"""

    type: Literal["token", "completed"]
    text: str = ""
    turn: ModelTurn | None = None


class ModelAdapter(Protocol):
    @property
    def model_name(self) -> str:
        ...

    def stream(
        self,
        messages: list[HarnessMessage],
        tools: list[Any],
    ) -> AsyncIterator[ModelStreamEvent]:
        ...


@dataclass(slots=True)
class ExecutionContext:
    """一次 Harness 执行过程中的运行时上下文。"""

    messages: list[HarnessMessage]
    stats_holder: dict[str, dict[str, Any]] = field(default_factory=dict)
    max_iterations: int = 5
    user_input: str = ""