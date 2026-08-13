from app.core.harness.context import (
    ContextManager,
    ContextPolicy,
)
from app.core.harness.runtime import (
    HarnessMessage,
    ToolCall,
)


def main() -> None:
    messages: list[HarnessMessage] = [
        HarnessMessage(
            role="system",
            content="你是一个测试 Agent。",
        )
    ]

    # 构造大量历史消息，故意让上下文超预算。
    for i in range(20):
        messages.append(
            HarnessMessage(
                role="user",
                content=f"历史问题 {i}：" + "这是一段历史内容。" * 30,
            )
        )
        messages.append(
            HarnessMessage(
                role="assistant",
                content=f"历史回答 {i}：" + "这是一段回答内容。" * 30,
            )
        )

    # 构造 Function Calling 消息块。
    messages.append(
        HarnessMessage(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(
                    id="call-test-1",
                    name="search",
                    arguments={"query": "测试"},
                )
            ],
        )
    )

    # 故意构造一个非常大的 Tool Result。
    messages.append(
        HarnessMessage(
            role="tool",
            tool_call_id="call-test-1",
            content="非常长的工具搜索结果。" * 1000,
        )
    )

    messages.append(
        HarnessMessage(
            role="user",
            content="请根据工具结果给我最终结论。",
        )
    )

    manager = ContextManager(
        policy=ContextPolicy(
            input_token_budget=800,
            max_tool_result_tokens=150,
            min_recent_blocks=3,
        )
    )

    prepared = manager.prepare(messages)

    stats = prepared.stats

    print("=== Context Stats ===")
    print(f"original_messages: {stats.original_messages}")
    print(f"final_messages:    {stats.final_messages}")
    print(f"original_tokens:   {stats.original_tokens}")
    print(f"final_tokens:      {stats.final_tokens}")
    print(f"dropped_messages:  {stats.dropped_messages}")
    print(f"dropped_blocks:    {stats.dropped_blocks}")
    print(
        "truncated_tools:  "
        f"{stats.truncated_tool_messages}"
    )
    print(f"compacted:         {stats.compacted}")
    print(f"over_budget:       {stats.over_budget}")

    assert stats.original_tokens > stats.final_tokens
    assert stats.final_tokens <= 800
    assert stats.dropped_blocks > 0
    assert stats.truncated_tool_messages == 1
    assert stats.compacted is True
    assert stats.over_budget is False

    # 检查 Function Calling 消息不能被拆散。
    assistant_tool_call_exists = any(
        message.role == "assistant"
        and any(
            call.id == "call-test-1"
            for call in message.tool_calls
        )
        for message in prepared.messages
    )

    tool_result_exists = any(
        message.role == "tool"
        and message.tool_call_id == "call-test-1"
        for message in prepared.messages
    )

    assert (
        assistant_tool_call_exists
        == tool_result_exists
    ), "assistant(tool_calls) 和 tool result 被拆散了"

    print()
    print("ContextManager check passed.")


if __name__ == "__main__":
    main()