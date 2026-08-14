from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from app.core.harness.checkpoint.models import (
    HarnessCheckpoint,
    RuntimeKind,
)

if TYPE_CHECKING:
    from app.core.harness.runtime.contracts import HarnessMessage



def encode_checkpoint(
    checkpoint: HarnessCheckpoint,
) -> dict[str, Any]:
    """将 HarnessCheckpoint 转成 JSON-safe dict。"""

    return {
        "version": 1,
        "checkpoint_id": str(checkpoint.checkpoint_id),
        "runtime": checkpoint.runtime,
        "next_iteration": checkpoint.next_iteration,
        "messages": [
            _encode_message(message)
            for message in checkpoint.messages
        ],
        "accumulated_text": checkpoint.accumulated_text,
        "user_input": checkpoint.user_input,
        "max_iterations": checkpoint.max_iterations,
        "metadata": checkpoint.metadata,
        "created_at": checkpoint.created_at.isoformat(),
    }


def decode_checkpoint(
    data: dict[str, Any],
) -> HarnessCheckpoint:
    """从 JSON-safe dict 恢复 HarnessCheckpoint。"""

    if data.get("version") != 1:
        raise ValueError(
            f"不支持的 checkpoint version: {data.get('version')}"
        )

    runtime = data["runtime"]

    if runtime not in {"function_calling", "react"}:
        raise ValueError(
            f"未知 checkpoint runtime: {runtime}"
        )

    return HarnessCheckpoint(
        checkpoint_id=uuid.UUID(data["checkpoint_id"]),
        runtime=cast(RuntimeKind, runtime),
        next_iteration=int(data["next_iteration"]),
        messages=[
            _decode_message(message)
            for message in data.get("messages", [])
        ],
        accumulated_text=data.get("accumulated_text", ""),
        user_input=data.get("user_input", ""),
        max_iterations=int(data.get("max_iterations", 5)),
        metadata=dict(data.get("metadata") or {}),
        created_at=datetime.fromisoformat(data["created_at"]),
    )


def _encode_message(
    message: HarnessMessage,
) -> dict[str, Any]:
    return {
        "role": message.role,
        "content": message.content,
        "tool_call_id": message.tool_call_id,
        "tool_calls": [
            {
                "id": tool_call.id,
                "name": tool_call.name,
                "arguments": tool_call.arguments,
            }
            for tool_call in message.tool_calls
        ],
    }


def _decode_message(
    data: dict[str, Any],
) -> "HarnessMessage":
    # 延迟导入，避免 checkpoint <-> runtime 循环依赖。
    from app.core.harness.runtime.contracts import (
        HarnessMessage,
        ToolCall,
    )

    role = data["role"]

    if role not in {
        "system",
        "user",
        "assistant",
        "tool",
    }:
        raise ValueError(
            f"未知 message role: {role}"
        )

    return HarnessMessage(
        role=cast(Any, role),
        content=data.get("content", ""),
        tool_call_id=data.get("tool_call_id"),
        tool_calls=[
            ToolCall(
                id=tool_call["id"],
                name=tool_call["name"],
                arguments=dict(
                    tool_call.get("arguments") or {}
                ),
            )
            for tool_call in data.get("tool_calls", [])
        ],
    )