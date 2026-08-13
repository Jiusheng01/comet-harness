from __future__ import annotations

import re
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


_ACTION_RE = re.compile(r"Action\s*:\s*(.+)")
_ACTION_INPUT_RE = re.compile(r"Action\s*Input\s*:\s*(.+)")
_FINAL_RE = re.compile(r"Final\s*Answer\s*:\s*(.*)", re.DOTALL)


class ReactRuntime:
    """Harness ReAct Runtime。

    负责：
    - 驱动 ReAct 多轮推理
    - 解析 Action / Action Input / Final Answer
    - 调度 ToolExecutor
    - 将 Observation 回灌模型上下文

    Runtime 不依赖 LangChain Message。
    """

    def __init__(
        self,
        model: ModelAdapter,
        tool_executor: ToolExecutor,
    ) -> None:
        self._model = model
        self._tool_executor = tool_executor

    async def run(
        self,
        ctx: ExecutionContext,
    ) -> AsyncGenerator[dict[str, Any], None]:
        tracer = get_tracer()

        for iteration in range(ctx.max_iterations):
            turn: ModelTurn | None = None
            response_text = ""

            async with tracer.llm_span(
                f"chat(ReAct):{self._model.model_name} (轮 {iteration + 1})",
                model_name=self._model.model_name,
                attributes={
                    "comet.chat.iteration": iteration + 1,
                    "comet.chat.mode": "react",
                    "comet.harness.runtime": "react",
                },
            ) as span:
                async for event in self._model.stream(
                    ctx.messages,
                    [],
                ):
                    if event.type == "token":
                        response_text += event.text

                    elif event.type == "completed":
                        turn = event.turn

                if turn is None:
                    turn = ModelTurn()

                # 某些 provider 的 completed 里有完整 text，
                # streaming 阶段可能没有 token。
                text = response_text or turn.text

                span.set_tokens(
                    input=turn.usage.input_tokens,
                    output=turn.usage.output_tokens,
                    cached=turn.usage.cached_tokens,
                    model_name=self._model.model_name,
                )

                span.set_payload(
                    "messages_count",
                    len(ctx.messages),
                )

                if text:
                    span.set_payload(
                        "response_preview",
                        text[:600],
                    )

            final_match = _FINAL_RE.search(text)

            if final_match:
                answer = final_match.group(1).strip()

                yield {
                    "type": "token",
                    "text": answer,
                }

                yield {
                    "type": "final",
                    "text": answer,
                }
                return

            action_match = _ACTION_RE.search(text)
            input_match = _ACTION_INPUT_RE.search(text)

            if not action_match:
                yield {
                    "type": "token",
                    "text": text,
                }

                yield {
                    "type": "final",
                    "text": text,
                }
                return

            tool_name = (
                action_match
                .group(1)
                .strip()
                .splitlines()[0]
                .strip()
            )

            query = (
                input_match
                .group(1)
                .strip()
                .splitlines()[0]
                .strip()
                if input_match
                else ctx.user_input
            )

            yield {
                "type": "tool_start",
                "tool": tool_name,
                "query": query,
            }

            result = await self._tool_executor.execute(
                tool_name=tool_name,
                args={"query": query},
            )

            yield result.to_event()

            ctx.messages.append(
                HarnessMessage(
                    role="assistant",
                    content=text,
                )
            )

            ctx.messages.append(
                HarnessMessage(
                    role="user",
                    content=f"Observation: {result.content}",
                )
            )

        yield {
            "type": "final",
            "text": "（多轮工具调用后仍未得到结论）",
        }