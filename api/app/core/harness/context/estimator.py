from __future__ import annotations

import json
from typing import Protocol

from app.core.harness.runtime.contracts import HarnessMessage
from app.core.rag.chunker import count_tokens


class TokenEstimator(Protocol):
    """Harness 调用模型前的 token 预算估算接口。"""

    def estimate_text(self, text: str) -> int:
        ...

    def estimate_message(self, message: HarnessMessage) -> int:
        ...


class TiktokenEstimator:
    """复用 Comet 现有 cl100k_base token 计数能力。

    注意：
    对非 cl100k_base 模型，这是预算估算而非模型真实 token 数。
    模型调用后的真实 token 仍以 usage_metadata 为准。
    """

    def estimate_text(self, text: str) -> int:
        if not text:
            return 0

        return count_tokens(text)

    def estimate_message(self, message: HarnessMessage) -> int:
        # role / message framing 的近似协议开销
        tokens = 4 + self.estimate_text(message.content)

        for call in message.tool_calls:
            tokens += self.estimate_text(call.name)

            arguments = json.dumps(
                call.arguments,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )

            tokens += self.estimate_text(arguments)

        return tokens