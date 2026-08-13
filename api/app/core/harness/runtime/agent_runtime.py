from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from app.core.agent.tracing import get_tracer
from app.core.harness.runtime.contracts import (
    ExecutionContext,
    HarnessMessage,
    ModelAdapter,
    ModelTurn,
)
from app.core.harness.tools.executor import ToolExecutor


class AgentRuntime:
    """Harness Agent Runtime。

    负责：
    - 驱动模型多轮执行
    - 解析统一 ToolCall
    - 调度 ToolExecutor
    - 将工具结果回灌模型上下文
    - 维护 Agent 执行循环

    Runtime 不直接依赖 ChatOpenAI / LangChain Message。
    """

    def __init__(
        self,
        model: ModelAdapter,
        tool_executor: ToolExecutor,
        model_tools: list[Any],
    ) -> None:
        self._model = model
        self._tool_executor = tool_executor
        self._model_tools = model_tools

    async def run(
        self,
        ctx: ExecutionContext,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """执行 Function Calling Agent Loop。"""

        full_text = ""
        tracer = get_tracer()

        for iteration in range(ctx.max_iterations):
            last_message_text = self._last_message_text(ctx.messages)

            turn: ModelTurn | None = None
            iteration_text = ""

            async with tracer.llm_span(
                f"chat:{self._model.model_name} (轮 {iteration + 1})",
                model_name=self._model.model_name,
                attributes={
                    "comet.chat.iteration": iteration + 1,
                    "comet.chat.tools_bound": len(self._model_tools),
                    "comet.harness.runtime": "agent",
                },
            ) as span:
                span.set_payload(
                    "messages_count",
                    len(ctx.messages),
                )

                if last_message_text:
                    span.set_payload(
                        "request_summary",
                        last_message_text[:600],
                    )

                async for event in self._model.stream(
                    ctx.messages,
                    self._model_tools,
                ):
                    if event.type == "token":
                        full_text += event.text
                        iteration_text += event.text

                        yield {
                            "type": "token",
                            "text": event.text,
                        }

                    elif event.type == "completed":
                        turn = event.turn

                if turn is None:
                    turn = ModelTurn()

                span.set_tokens(
                    input=turn.usage.input_tokens,
                    output=turn.usage.output_tokens,
                    cached=turn.usage.cached_tokens,
                    model_name=self._model.model_name,
                )

                span.set_payload(
                    "tool_calls_count",
                    len(turn.tool_calls),
                )

                if iteration_text:
                    span.set_payload(
                        "response_preview",
                        iteration_text[:600],
                    )
                elif turn.tool_calls:
                    span.set_payload(
                        "response_preview",
                        "(本轮无文字输出,触发工具:"
                        + ", ".join(
                            call.name
                            for call in turn.tool_calls[:5]
                        )
                        + ")",
                    )

            # 某些 provider 可能最终返回 text，
            # 但 streaming 阶段没有产生 token。
            if not iteration_text and turn.text and not turn.tool_calls:
                full_text += turn.text

                yield {
                    "type": "token",
                    "text": turn.text,
                }

            # 没有工具调用，本轮就是最终答案。
            if not turn.tool_calls:
                yield {
                    "type": "final",
                    "text": full_text,
                }
                return

            # 将 assistant 的工具调用写入 Harness 上下文。
            ctx.messages.append(
                HarnessMessage(
                    role="assistant",
                    content=turn.text,
                    tool_calls=turn.tool_calls,
                )
            )

            for tool_call in turn.tool_calls:
                query = str(
                    tool_call.arguments.get("query", "") or ""
                )

                yield {
                    "type": "tool_start",
                    "tool": tool_call.name,
                    "query": query,
                }

                result = await self._tool_executor.execute(
                    tool_name=tool_call.name,
                    args=tool_call.arguments,
                )

                yield result.to_event()

                # 工具结果回灌给下一轮模型。
                ctx.messages.append(
                    HarnessMessage(
                        role="tool",
                        content=result.content,
                        tool_call_id=tool_call.id,
                    )
                )

        yield {
            "type": "final",
            "text": full_text or "（未能生成回答）",
        }

    @staticmethod
    def _last_message_text(
        messages: list[HarnessMessage],
    ) -> str:
        for message in reversed(messages):
            if message.content:
                return message.content
        return ""