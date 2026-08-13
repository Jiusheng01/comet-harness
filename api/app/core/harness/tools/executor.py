from __future__ import annotations

import ast
import json
import time
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import StructuredTool

from app.core.agent.tracing import get_tracer


MAX_TOOL_RESULT_PREVIEW = 600


def format_observation(observation: object) -> str:
    """将不同类型的工具返回值统一转换成适合回灌给 LLM 的文本。"""

    if isinstance(observation, str):
        text = observation.strip()

        if text and text[0] in "[{(" and text[-1] in "]})":
            try:
                parsed = ast.literal_eval(text)
                if not isinstance(parsed, str):
                    return format_observation(parsed)
            except (ValueError, SyntaxError):
                pass

        return text

    if isinstance(observation, list):
        parts: list[str] = []

        for item in observation:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                    continue

            text_attr = getattr(item, "text", None)
            if isinstance(text_attr, str):
                parts.append(text_attr)
                continue

            try:
                parts.append(
                    json.dumps(item, ensure_ascii=False, indent=2)
                )
            except (TypeError, ValueError):
                parts.append(str(item))

        return "\n\n".join(
            part.strip() for part in parts if part
        )

    if isinstance(observation, dict):
        text = observation.get("text")

        if isinstance(text, str):
            return text

        try:
            return json.dumps(
                observation,
                ensure_ascii=False,
                indent=2,
            )
        except (TypeError, ValueError):
            return str(observation)

    text_attr = getattr(observation, "text", None)

    if isinstance(text_attr, str):
        return text_attr

    return str(observation)


def truncate_preview(text: str) -> str:
    if len(text) <= MAX_TOOL_RESULT_PREVIEW:
        return text

    return text[:MAX_TOOL_RESULT_PREVIEW].rstrip() + "..."


@dataclass
class ToolExecutionResult:
    tool: str
    query: str
    status: str
    content: str
    stats: dict[str, Any]
    latency_ms: int
    cached: bool = False

    def to_event(self) -> dict[str, Any]:
        event = {
            "type": "tool_result",
            "tool": self.tool,
            "query": self.query,
            "status": self.status,
            "text": truncate_preview(self.content),
            "stats": self.stats,
            "latency_ms": self.latency_ms,
        }

        if self.cached:
            event["cached"] = True

        return event


class ToolExecutor:
    """Harness 中统一负责工具查找、执行、缓存和观测。"""

    def __init__(
        self,
        tools: list[StructuredTool],
        stats_holder: dict[str, dict] | None = None,
    ) -> None:
        self._tool_map = {tool.name: tool for tool in tools}
        self._stats_holder = (
            stats_holder if stats_holder is not None else {}
        )

        # 当前 Run 内缓存相同工具 + 相同参数的结果
        self._call_cache: dict[str, str] = {}

    @staticmethod
    def _build_cache_key(
        tool_name: str,
        args: dict[str, Any],
    ) -> str:
        try:
            args_text = json.dumps(
                args,
                ensure_ascii=False,
                sort_keys=True,
            )
        except (TypeError, ValueError):
            args_text = str(args)

        return f"{tool_name}:{args_text}"

    async def execute(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
    ) -> ToolExecutionResult:
        args = args or {}

        query = str(args.get("query", "") or "")
        cache_key = self._build_cache_key(tool_name, args)

        cached = self._call_cache.get(cache_key)

        if cached is not None:
            return ToolExecutionResult(
                tool=tool_name,
                query=query,
                status="success",
                content=cached,
                stats={},
                latency_ms=0,
                cached=True,
            )

        tool = self._tool_map.get(tool_name)

        if tool is None:
            return ToolExecutionResult(
                tool=tool_name,
                query=query,
                status="error",
                content=f"未知工具：{tool_name}",
                stats={},
                latency_ms=0,
            )

        status = "success"
        started_at = time.monotonic()

        tracer = get_tracer()

        async with tracer.span(
            f"工具:{tool_name}",
            span_type="tool_call",
            attributes={
                "comet.tool.name": tool_name,
                "comet.tool.query": query[:200],
            },
        ) as span:
            try:
                observation = await tool.ainvoke(args)

            except Exception as exc:
                observation = f"工具执行失败：{exc}"
                status = "error"
                span.mark_error(str(exc))

            observation_text = (
                str(observation) if observation else ""
            )

            span.set_payload("status", status)
            span.set_payload(
                "output_chars",
                len(observation_text),
            )

            if observation_text:
                span.set_payload(
                    "output_preview",
                    observation_text[:600],
                )

            if query:
                span.set_payload(
                    "tool_query",
                    query[:300],
                )

        latency_ms = int(
            (time.monotonic() - started_at) * 1000
        )

        stats = self._stats_holder.pop(tool_name, {})

        formatted = format_observation(observation)

        if status == "success":
            self._call_cache[cache_key] = formatted

        return ToolExecutionResult(
            tool=tool_name,
            query=query,
            status=status,
            content=formatted,
            stats=stats,
            latency_ms=latency_ms,
        )