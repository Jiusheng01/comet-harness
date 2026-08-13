"""Agent 编排：方案B 双路径工具循环，产出统一事件流。

- 强模型（支持 function calling）：bind_tools + 流式工具循环，原生决定调用哪个工具。
- 弱模型：ToolOrchestrator（prompt 模拟 ReAct），解析 Action/Action Input 手动调工具。

两条路径都产出统一事件 dict：
  {"type": "tool_start", "tool", "query"} /
  {"type": "tool_result", "tool", "query", "status", "text", "stats", "latency_ms"} /
  {"type": "token", "text"} / {"type": "final", "text"}
引用由工具执行时写入外部传入的 citations 列表，编排结束后由调用方读取。

工具统计（命中数 / 实体数 / 网页数等）由各工具写入 ctx.stats_holder[tool_key]，
统一由 Harness ToolExecutor 读取并附加到 tool_result 事件。
"""
import re
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI

from app.core.agent.prompt_renderer import render_agent_prompt
from app.core.agent.tracing import get_tracer

from app.core.harness.tools.executor import ToolExecutor

MAX_TOOL_ITERATIONS = 5

async def run_function_calling(
    model: ChatOpenAI,
    tools: list[StructuredTool],
    messages: list,
    stats_holder: dict[str, dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """强模型路径：原生 function calling 流式工具循环。"""

    model_with_tools = model.bind_tools(tools) if tools else model
    full_text = ""
    stats_holder = stats_holder if stats_holder is not None else {}
    tool_executor = ToolExecutor(
        tools=tools,
        stats_holder=stats_holder,
    )

    # 取真实 model_name 用于成本核算(LangChain ChatOpenAI 的 model_name 字段)
    chat_model_name = getattr(model, "model_name", None) or getattr(model, "model", "chat")
    tracer = get_tracer()

    for iteration in range(MAX_TOOL_ITERATIONS):
        # 每轮 LLM 流式调用包一个 llm_call span,流完后从 usage_metadata 抽 token
        # 抓最后一条 user/tool 消息做请求摘要
        last_msg_text = ""
        for m in reversed(messages):
            content = getattr(m, "content", None)
            if isinstance(content, str) and content:
                last_msg_text = content
                break
        async with tracer.llm_span(
            f"chat:{chat_model_name} (轮 {iteration + 1})",
            model_name=chat_model_name,
            attributes={
                "comet.chat.iteration": iteration + 1,
                "comet.chat.tools_bound": len(tools),
            },
        ) as lsp:
            lsp.set_payload("messages_count", len(messages))
            if last_msg_text:
                lsp.set_payload("request_summary", last_msg_text[:600])
            gathered = None
            iter_text = ""
            async for chunk in model_with_tools.astream(messages):
                if chunk.content:
                    text = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                    full_text += text
                    iter_text += text
                    yield {"type": "token", "text": text}
                gathered = chunk if gathered is None else gathered + chunk
            # 抽 token 用量(stream_usage=True 后流尾的 chunk 带 usage_metadata)
            usage = getattr(gathered, "usage_metadata", None) or {}
            in_t = int(usage.get("input_tokens", 0) or 0)
            out_t = int(usage.get("output_tokens", 0) or 0)
            cached = int((usage.get("input_token_details") or {}).get("cache_read", 0) or 0)
            lsp.set_tokens(input=in_t, output=out_t, cached=cached, model_name=chat_model_name)
            tool_calls = getattr(gathered, "tool_calls", None) or []
            lsp.set_payload("tool_calls_count", len(tool_calls))
            if iter_text:
                lsp.set_payload("response_preview", iter_text[:600])
            elif tool_calls:
                # 没有文本输出但触发了工具:展示工具调用意图
                lsp.set_payload(
                    "response_preview",
                    "(本轮无文字输出,触发工具:" + ", ".join(tc.get("name", "?") for tc in tool_calls[:5]) + ")",
                )

        if not tool_calls:
            # 无工具调用 → 已是最终回答
            yield {"type": "final", "text": full_text}
            return

        # 有工具调用：执行后把结果回灌，继续循环
        messages.append(gathered)
        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("args", {}) or {}
            query = str(args.get("query", "") or "")

            yield {
                "type": "tool_start",
                "tool": name,
                "query": query,
            }

            result = await tool_executor.execute(
                tool_name=name,
                args=args,
            )

            yield result.to_event()

            messages.append(
                ToolMessage(
                    content=result.content,
                    tool_call_id=tc.get("id", name),
                )
            )
    # 达到最大迭代仍未收敛：用现有内容兜底
    yield {"type": "final", "text": full_text or "（未能生成回答）"}


_ACTION_RE = re.compile(r"Action\s*:\s*(.+)")
_ACTION_INPUT_RE = re.compile(r"Action\s*Input\s*:\s*(.+)")
_FINAL_RE = re.compile(r"Final\s*Answer\s*:\s*(.*)", re.DOTALL)


async def run_react(
    model: ChatOpenAI,
    tools: list[StructuredTool],
    user_text: str,
    history: list,
    system_prompt: str,
    stats_holder: dict[str, dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """弱模型路径：prompt 模拟 ReAct，手动解析并调用工具。"""
    sys = render_agent_prompt(
        "react.jinja2",
        tools=[{"name": t.name, "description": t.description} for t in tools],
        system_prompt=system_prompt,
    )
    convo: list = [SystemMessage(content=sys), *history, HumanMessage(content=user_text)]
    stats_holder = stats_holder if stats_holder is not None else {}
    tool_executor = ToolExecutor(
        tools=tools,
        stats_holder=stats_holder,
    )
    # 取真实 model_name 用于 token / cost 记账
    react_model_name = getattr(model, "model_name", None) or getattr(model, "model", "chat")
    tracer = get_tracer()

    for iteration in range(MAX_TOOL_ITERATIONS):
        async with tracer.llm_span(
            f"chat(ReAct):{react_model_name} (轮 {iteration + 1})",
            model_name=react_model_name,
            attributes={
                "comet.chat.iteration": iteration + 1,
                "comet.chat.mode": "react",
            },
        ) as lsp:
            resp = await model.ainvoke(convo)
            usage = getattr(resp, "usage_metadata", None) or {}
            in_t = int(usage.get("input_tokens", 0) or 0)
            out_t = int(usage.get("output_tokens", 0) or 0)
            cached = int((usage.get("input_token_details") or {}).get("cache_read", 0) or 0)
            lsp.set_tokens(input=in_t, output=out_t, cached=cached, model_name=react_model_name)
        text = resp.content if isinstance(resp.content, str) else str(resp.content)

        final_match = _FINAL_RE.search(text)
        if final_match:
            answer = final_match.group(1).strip()
            yield {"type": "token", "text": answer}
            yield {"type": "final", "text": answer}
            return

        action_match = _ACTION_RE.search(text)
        input_match = _ACTION_INPUT_RE.search(text)
        if not action_match:
            # 没有 Action 也没有 Final，把整段当回答兜底
            yield {"type": "token", "text": text}
            yield {"type": "final", "text": text}
            return

        tool_name = action_match.group(1).strip().splitlines()[0].strip()
        query = (input_match.group(1).strip().splitlines()[0].strip() if input_match else user_text)
        yield {"type": "tool_start", "tool": tool_name, "query": query}

        result = await tool_executor.execute(
            tool_name=tool_name,
            args={"query": query},
        )
        yield result.to_event()
        formatted = result.content
        # 把模型上一轮输出 + Observation 回灌
        convo.append(AIMessage(content=text))
        convo.append(HumanMessage(content=f"Observation: {formatted}"))

    yield {"type": "final", "text": "（多轮工具调用后仍未得到结论）"}


__all__ = ["run_function_calling", "run_react", "MAX_TOOL_ITERATIONS"]
