from __future__ import annotations

import re
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from app.core.agent.tracing import get_tracer
from app.core.harness.checkpoint import (
    CheckpointStore,
    HarnessCheckpoint,
)
from app.core.harness.context import ContextManager
from app.core.harness.runtime.contracts import (
    ExecutionContext,
    HarnessMessage,
    ModelAdapter,
    ModelTurn,
)
from app.core.harness.tools.executor import ToolExecutor


_ACTION_RE = re.compile(r"Action\s*:\s*(.+)")
_ACTION_INPUT_RE = re.compile(
    r"Action\s*Input\s*:\s*(.+)"
)
_FINAL_RE = re.compile(
    r"Final\s*Answer\s*:\s*(.*)",
    re.DOTALL,
)


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
        context_manager: ContextManager,
        checkpoint_store: CheckpointStore | None = None,
    ) -> None:
        self._model = model
        self._tool_executor = tool_executor
        self._context_manager = context_manager
        self._checkpoint_store = checkpoint_store

    async def run(
        self,
        ctx: ExecutionContext,
        *,
        checkpoint_id: uuid.UUID | None = None,
        start_iteration: int = 0,
        cleanup_checkpoint_on_finish: bool = True,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """执行 ReAct Agent Loop。"""

        tracer = get_tracer()

        # 第一轮模型调用之前建立 checkpoint。
        if (
            checkpoint_id is not None
            and self._checkpoint_store is not None
            and start_iteration == 0
        ):
            await self._checkpoint_store.save(
                HarnessCheckpoint(
                    checkpoint_id=checkpoint_id,
                    runtime="react",
                    next_iteration=0,
                    messages=ctx.messages,
                    user_input=ctx.user_input,
                    max_iterations=ctx.max_iterations,
                    metadata={
                        "model_name": self._model.model_name,
                    },
                )
            )

        for iteration in range(
            start_iteration,
            ctx.max_iterations,
        ):
            prepared = self._context_manager.prepare(
                ctx.messages
            )

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
                    prepared.messages,
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
                    len(prepared.messages),
                )

                span.set_payload(
                    "context.original_messages",
                    prepared.stats.original_messages,
                )

                span.set_payload(
                    "context.final_messages",
                    prepared.stats.final_messages,
                )

                span.set_payload(
                    "context.original_tokens",
                    prepared.stats.original_tokens,
                )

                span.set_payload(
                    "context.final_tokens",
                    prepared.stats.final_tokens,
                )

                span.set_payload(
                    "context.dropped_messages",
                    prepared.stats.dropped_messages,
                )

                span.set_payload(
                    "context.dropped_blocks",
                    prepared.stats.dropped_blocks,
                )

                span.set_payload(
                    "context.truncated_tool_messages",
                    prepared.stats.truncated_tool_messages,
                )

                span.set_payload(
                    "context.compacted",
                    prepared.stats.compacted,
                )

                span.set_payload(
                    "context.over_budget",
                    prepared.stats.over_budget,
                )

                if text:
                    span.set_payload(
                        "response_preview",
                        text[:600],
                    )

            final_match = _FINAL_RE.search(text)

            if final_match:
                answer = (
                    final_match
                    .group(1)
                    .strip()
                )

                if (
                    cleanup_checkpoint_on_finish
                    and checkpoint_id is not None
                    and self._checkpoint_store is not None
                ):
                    await self._checkpoint_store.delete(
                        checkpoint_id
                    )

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
            input_match = _ACTION_INPUT_RE.search(
                text
            )

            if not action_match:
                if (
                    cleanup_checkpoint_on_finish
                    and checkpoint_id is not None
                    and self._checkpoint_store is not None
                ):
                    await self._checkpoint_store.delete(
                        checkpoint_id
                    )

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
                args={
                    "query": query,
                },
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
                    content=(
                        f"Observation: {result.content}"
                    ),
                )
            )

            # Action + Observation 都写入上下文后，
            # 才推进 checkpoint。
            if (
                checkpoint_id is not None
                and self._checkpoint_store is not None
            ):
                await self._checkpoint_store.save(
                    HarnessCheckpoint(
                        checkpoint_id=checkpoint_id,
                        runtime="react",
                        next_iteration=iteration + 1,
                        messages=ctx.messages,
                        user_input=ctx.user_input,
                        max_iterations=ctx.max_iterations,
                        metadata={
                            "model_name": self._model.model_name,
                        },
                    )
                )

        if (
            cleanup_checkpoint_on_finish
            and checkpoint_id is not None
            and self._checkpoint_store is not None
        ):
            await self._checkpoint_store.delete(
                checkpoint_id
            )

        yield {
            "type": "final",
            "text": "（多轮工具调用后仍未得到结论）",
        }

    async def resume(
        self,
        checkpoint_id: uuid.UUID,
        *,
        cleanup_checkpoint_on_finish: bool = True,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """从 ReAct checkpoint 恢复执行。"""

        if self._checkpoint_store is None:
            raise RuntimeError(
                "ReactRuntime 未配置 checkpoint_store"
            )

        checkpoint = await self._checkpoint_store.load(
            checkpoint_id
        )

        if checkpoint is None:
            raise ValueError(
                f"checkpoint 不存在: {checkpoint_id}"
            )

        if checkpoint.runtime != "react":
            raise ValueError(
                "checkpoint runtime 类型不匹配: "
                f"{checkpoint.runtime}"
            )

        ctx = ExecutionContext(
            messages=checkpoint.messages,
            max_iterations=checkpoint.max_iterations,
            user_input=checkpoint.user_input,
        )

        async for event in self.run(
            ctx,
            checkpoint_id=checkpoint.checkpoint_id,
            start_iteration=checkpoint.next_iteration,
            cleanup_checkpoint_on_finish=(
                cleanup_checkpoint_on_finish
            ),
        ):
            yield event
