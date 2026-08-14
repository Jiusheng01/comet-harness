import json
import uuid

from app.core.harness.checkpoint import HarnessCheckpoint
from app.core.harness.checkpoint.codec import (
    decode_checkpoint,
    encode_checkpoint,
)
from app.core.harness.runtime import (
    HarnessMessage,
    ToolCall,
)


def main() -> None:
    checkpoint = HarnessCheckpoint(
        checkpoint_id=uuid.uuid4(),
        runtime="function_calling",
        next_iteration=2,
        messages=[
            HarnessMessage(
                role="user",
                content="现在几点？",
            ),
            HarnessMessage(
                role="assistant",
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="datetime",
                        arguments={
                            "query": "current time",
                        },
                    )
                ],
            ),
            HarnessMessage(
                role="tool",
                content="2026-08-14 09:41:00",
                tool_call_id="call_1",
            ),
        ],
        accumulated_text="",
        user_input="现在几点？",
        max_iterations=5,
        metadata={
            "model_name": "qwen-test",
        },
    )

    encoded = encode_checkpoint(checkpoint)

    # 真正经过一次 JSON 序列化，
    # 防止只是“看起来像 dict”但里面仍有 Python 对象。
    json_text = json.dumps(
        encoded,
        ensure_ascii=False,
    )

    decoded = decode_checkpoint(
        json.loads(json_text)
    )

    assert decoded.checkpoint_id == checkpoint.checkpoint_id
    assert decoded.runtime == "function_calling"
    assert decoded.next_iteration == 2
    assert decoded.user_input == "现在几点？"
    assert decoded.max_iterations == 5
    assert decoded.metadata["model_name"] == "qwen-test"

    assert len(decoded.messages) == 3

    assistant = decoded.messages[1]
    assert assistant.role == "assistant"
    assert len(assistant.tool_calls) == 1
    assert assistant.tool_calls[0].id == "call_1"
    assert assistant.tool_calls[0].name == "datetime"
    assert (
        assistant.tool_calls[0].arguments["query"]
        == "current time"
    )

    tool = decoded.messages[2]
    assert tool.role == "tool"
    assert tool.tool_call_id == "call_1"
    assert tool.content == "2026-08-14 09:41:00"

    print("json bytes:", len(json_text.encode("utf-8")))
    print("messages:", len(decoded.messages))
    print(
        "tool:",
        decoded.messages[1].tool_calls[0].name,
    )
    print()
    print("Checkpoint codec round-trip check passed.")


if __name__ == "__main__":
    main()