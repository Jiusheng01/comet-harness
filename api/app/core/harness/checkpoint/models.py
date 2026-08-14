from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from app.core.harness.runtime.contracts import HarnessMessage


RuntimeKind = Literal["function_calling", "react"]


@dataclass(slots=True)
class HarnessCheckpoint:
    """一次 Harness 执行的可恢复快照。"""

    checkpoint_id: uuid.UUID
    runtime: RuntimeKind

    # 恢复后应该从哪个 iteration 继续执行，0-based。
    next_iteration: int
    messages: list["HarnessMessage"]

    accumulated_text: str = ""
    user_input: str = ""
    max_iterations: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )