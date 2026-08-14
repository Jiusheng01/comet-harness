"""Agent 编排入口：组装 Harness 双运行时，产出统一事件流。

- 强模型（支持 Function Calling）：
  LangChainModelAdapter + AgentRuntime 驱动原生工具调用循环。

- 弱模型：
  ReactRuntime 基于 ReAct Prompt 解析 Action / Action Input，
  并通过统一 ToolExecutor 执行工具。

两条路径都产出统一事件：
  {"type": "tool_start", "tool", "query"} /
  {"type": "tool_result", "tool", "query", "status", "text", "stats", "latency_ms"} /
  {"type": "token", "text"} /
  {"type": "final", "text"}

工具统计由各工具写入 stats_holder，
统一由 Harness ToolExecutor 读取并附加到 tool_result 事件。

Checkpoint / Resume：
- 未传 checkpoint_store + checkpoint_id：保持原来的普通运行模式；
- 同时传入：
  - checkpoint 不存在 -> 从头 run，并持续保存 checkpoint；
  - checkpoint 已存在 -> 从持久化状态 resume。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI

from app.core.agent.prompt_renderer import render_agent_prompt
from app.core.harness.adapters import (
    LangChainModelAdapter,
    from_langchain_messages,
)
from app.core.harness.context import ContextManager
from app.core.harness.runtime import (
    AgentRuntime,
    ExecutionContext,
    HarnessMessage,
    ReactRuntime,
)
from app.core.harness.tools.executor import ToolExecutor

if TYPE_CHECKING:
    from app.core.harness.checkpoint.store import CheckpointStore


MAX_TOOL_ITERATIONS = 5


def _validate_checkpoint_args(
    checkpoint_store: CheckpointStore | None,
    checkpoint_id: uuid.UUID | None,
) -> None:
    """checkpoint store 与 id 必须同时传入或同时省略。"""

    if (checkpoint_store is None) != (checkpoint_id is None):
        raise ValueError(
            "checkpoint_store 和 checkpoint_id 必须同时提供"
        )


async def _has_checkpoint(
    checkpoint_store: CheckpointStore | None,
    checkpoint_id: uuid.UUID | None,
) -> bool:
    """判断当前执行是否已经存在可恢复 checkpoint。"""

    if checkpoint_store is None or checkpoint_id is None:
        return False

    checkpoint = await checkpoint_store.load(
        checkpoint_id
    )

    return checkpoint is not None


async def run_function_calling(
    model: ChatOpenAI,
    tools: list[StructuredTool],
    messages: list,
    stats_holder: dict[str, dict] | None = None,
    checkpoint_store: CheckpointStore | None = None,
    checkpoint_id: uuid.UUID | None = None,
) -> AsyncGenerator[dict, None]:
    """强模型路径：由 Harness AgentRuntime 驱动 Function Calling。

    checkpoint_store + checkpoint_id 均未提供时，
    保持原来的无持久化运行方式。

    两者均提供时：
    - checkpoint 已存在：resume；
    - checkpoint 不存在：run，并在稳定边界保存 checkpoint。
    """

    _validate_checkpoint_args(
        checkpoint_store,
        checkpoint_id,
    )

    stats_holder = (
        stats_holder
        if stats_holder is not None
        else {}
    )

    model_adapter = LangChainModelAdapter(
        model
    )

    tool_executor = ToolExecutor(
        tools=tools,
        stats_holder=stats_holder,
    )

    context_manager = ContextManager()

    ctx = ExecutionContext(
        messages=from_langchain_messages(
            messages
        ),
        stats_holder=stats_holder,
        max_iterations=MAX_TOOL_ITERATIONS,
    )

    runtime = AgentRuntime(
        model=model_adapter,
        tool_executor=tool_executor,
        model_tools=tools,
        context_manager=context_manager,
        checkpoint_store=checkpoint_store,
    )

    if await _has_checkpoint(
        checkpoint_store,
        checkpoint_id,
    ):
        assert checkpoint_id is not None

        async for event in runtime.resume(
            checkpoint_id
        ):
            yield event

        return

    async for event in runtime.run(
        ctx,
        checkpoint_id=checkpoint_id,
    ):
        yield event


async def run_react(
    model: ChatOpenAI,
    tools: list[StructuredTool],
    user_text: str,
    history: list,
    system_prompt: str,
    stats_holder: dict[str, dict] | None = None,
    checkpoint_store: CheckpointStore | None = None,
    checkpoint_id: uuid.UUID | None = None,
) -> AsyncGenerator[dict, None]:
    """弱模型路径：由 Harness ReactRuntime 驱动 ReAct 工具循环。

    checkpoint_store + checkpoint_id 均未提供时，
    保持原来的无持久化运行方式。

    两者均提供时：
    - checkpoint 已存在：resume；
    - checkpoint 不存在：run，并在稳定边界保存 checkpoint。
    """

    _validate_checkpoint_args(
        checkpoint_store,
        checkpoint_id,
    )

    react_prompt = render_agent_prompt(
        "react.jinja2",
        tools=[
            {
                "name": tool.name,
                "description": tool.description,
            }
            for tool in tools
        ],
        system_prompt=system_prompt,
    )

    stats_holder = (
        stats_holder
        if stats_holder is not None
        else {}
    )

    messages = [
        HarnessMessage(
            role="system",
            content=react_prompt,
        ),
        *from_langchain_messages(
            history
        ),
        HarnessMessage(
            role="user",
            content=user_text,
        ),
    ]

    ctx = ExecutionContext(
        messages=messages,
        stats_holder=stats_holder,
        max_iterations=MAX_TOOL_ITERATIONS,
        user_input=user_text,
    )

    context_manager = ContextManager()

    model_adapter = LangChainModelAdapter(
        model
    )

    tool_executor = ToolExecutor(
        tools=tools,
        stats_holder=stats_holder,
    )

    runtime = ReactRuntime(
        model=model_adapter,
        tool_executor=tool_executor,
        context_manager=context_manager,
        checkpoint_store=checkpoint_store,
    )

    if await _has_checkpoint(
        checkpoint_store,
        checkpoint_id,
    ):
        assert checkpoint_id is not None

        async for event in runtime.resume(
            checkpoint_id
        ):
            yield event

        return

    async for event in runtime.run(
        ctx,
        checkpoint_id=checkpoint_id,
    ):
        yield event


__all__ = [
    "run_function_calling",
    "run_react",
    "MAX_TOOL_ITERATIONS",
]