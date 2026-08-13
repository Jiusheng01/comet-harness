from __future__ import annotations

from dataclasses import dataclass

from app.core.harness.context.estimator import (
    TiktokenEstimator,
    TokenEstimator,
)
from app.core.harness.runtime.contracts import HarnessMessage


@dataclass(slots=True)
class ContextPolicy:
    """Harness 上下文预算策略。

    input_token_budget 是 Harness 自己的输入预算，
    不是模型官方 context window。
    后续再从模型配置动态读取。
    """

    input_token_budget: int = 8000
    max_tool_result_tokens: int = 1200
    min_recent_blocks: int = 4


@dataclass(slots=True)
class ContextStats:
    original_tokens: int = 0
    final_tokens: int = 0
    original_messages: int = 0
    final_messages: int = 0
    dropped_messages: int = 0
    dropped_blocks: int = 0
    truncated_tool_messages: int = 0
    over_budget: bool = False

    @property
    def compacted(self) -> bool:
        return (
            self.dropped_messages > 0
            or self.truncated_tool_messages > 0
        )


@dataclass(slots=True)
class PreparedContext:
    messages: list[HarnessMessage]
    stats: ContextStats


class ContextManager:
    """构造满足 token budget 的模型上下文视图。

    ExecutionContext.messages 保存完整执行轨迹；
    本类只决定当前这一轮应该给模型看哪些消息。
    """

    def __init__(
        self,
        policy: ContextPolicy | None = None,
        estimator: TokenEstimator | None = None,
    ) -> None:
        self._policy = policy or ContextPolicy()
        self._estimator = estimator or TiktokenEstimator()

    def prepare(
        self,
        messages: list[HarnessMessage],
    ) -> PreparedContext:
        copied = [
            self._copy_message(message)
            for message in messages
        ]

        stats = ContextStats(
            original_tokens=self._estimate_messages(copied),
            original_messages=len(copied),
        )

        # Phase 1:
        # 先压缩超长 Tool Result。
        for index, message in enumerate(copied):
            if message.role != "tool":
                continue

            tool_tokens = self._estimator.estimate_text(
                message.content
            )

            if (
                tool_tokens
                <= self._policy.max_tool_result_tokens
            ):
                continue

            copied[index] = HarnessMessage(
                role=message.role,
                content=self._truncate_text(
                    message.content,
                    self._policy.max_tool_result_tokens,
                ),
                tool_call_id=message.tool_call_id,
                tool_calls=list(message.tool_calls),
            )

            stats.truncated_tool_messages += 1

        # System Message 始终优先保留。
        system_messages = [
            message
            for message in copied
            if message.role == "system"
        ]

        blocks = self._build_blocks(copied)

        selected_blocks = self._select_blocks(
            system_messages=system_messages,
            blocks=blocks,
            budget=self._policy.input_token_budget,
        )

        final_messages = list(system_messages)

        for block in selected_blocks:
            final_messages.extend(block)

        stats.final_tokens = self._estimate_messages(
            final_messages
        )
        stats.final_messages = len(final_messages)

        stats.dropped_messages = (
            stats.original_messages
            - stats.final_messages
        )

        stats.dropped_blocks = (
            len(blocks)
            - len(selected_blocks)
        )

        stats.over_budget = (
            stats.final_tokens
            > self._policy.input_token_budget
        )

        return PreparedContext(
            messages=final_messages,
            stats=stats,
        )

    def _build_blocks(
        self,
        messages: list[HarnessMessage],
    ) -> list[list[HarnessMessage]]:
        """把消息构造成不可拆分的 Context Block。

        普通消息各自是一个 block。

        Function Calling:
        assistant(tool_calls) + 后续 tool messages 整体保留，
        避免产生孤立 ToolMessage。

        ReAct:
        assistant(Action) + user(Observation) 整体保留，
        避免压缩后破坏推理轨迹语义。
        """

        non_system = [
            message
            for message in messages
            if message.role != "system"
        ]

        blocks: list[list[HarnessMessage]] = []
        index = 0

        while index < len(non_system):
            message = non_system[index]

            # Function Calling:
            # assistant(tool_calls) + tool results 必须整体保留。
            if (
                message.role == "assistant"
                and message.tool_calls
            ):
                block = [message]
                index += 1

                while (
                    index < len(non_system)
                    and non_system[index].role == "tool"
                ):
                    block.append(non_system[index])
                    index += 1

                blocks.append(block)
                continue

            # ReAct:
            # Action + Observation 必须整体保留。
            if (
                message.role == "assistant"
                and index + 1 < len(non_system)
                and non_system[index + 1].role == "user"
                and non_system[index + 1].content.startswith("Observation:")
            ):
                blocks.append(
                    [
                        message,
                        non_system[index + 1],
                    ]
                )
                index += 2
                continue

            blocks.append([message])
            index += 1

        return blocks

    def _select_blocks(
        self,
        *,
        system_messages: list[HarnessMessage],
        blocks: list[list[HarnessMessage]],
        budget: int,
    ) -> list[list[HarnessMessage]]:
        if not blocks:
            return []

        recent_count = min(
            self._policy.min_recent_blocks,
            len(blocks),
        )

        split_index = len(blocks) - recent_count

        older_blocks = blocks[:split_index]
        selected = list(blocks[split_index:])

        # recent 本身超预算时，从最旧 recent block 开始淘汰。
        # 至少保留最后一个 block。
        while (
            len(selected) > 1
            and self._estimate_context(
                system_messages,
                selected,
            )
            > budget
        ):
            selected.pop(0)

        # 如果还有剩余预算，再从近到远把历史补回来。
        for block in reversed(older_blocks):
            candidate = [
                block,
                *selected,
            ]

            if (
                self._estimate_context(
                    system_messages,
                    candidate,
                )
                <= budget
            ):
                selected.insert(0, block)

        return selected

    def _estimate_context(
        self,
        system_messages: list[HarnessMessage],
        blocks: list[list[HarnessMessage]],
    ) -> int:
        messages = list(system_messages)

        for block in blocks:
            messages.extend(block)

        return self._estimate_messages(messages)

    def _estimate_messages(
        self,
        messages: list[HarnessMessage],
    ) -> int:
        return sum(
            self._estimator.estimate_message(message)
            for message in messages
        )

    def _truncate_text(
        self,
        text: str,
        max_tokens: int,
    ) -> str:
        suffix = (
            "\n\n[Harness: tool output truncated "
            "by context budget]"
        )

        suffix_tokens = self._estimator.estimate_text(
            suffix
        )

        content_budget = max(
            1,
            max_tokens - suffix_tokens,
        )

        low = 0
        high = len(text)

        while low < high:
            mid = (low + high + 1) // 2

            tokens = self._estimator.estimate_text(
                text[:mid]
            )

            if tokens <= content_budget:
                low = mid
            else:
                high = mid - 1

        return text[:low] + suffix

    @staticmethod
    def _copy_message(
        message: HarnessMessage,
    ) -> HarnessMessage:
        return HarnessMessage(
            role=message.role,
            content=message.content,
            tool_call_id=message.tool_call_id,
            tool_calls=list(message.tool_calls),
        )