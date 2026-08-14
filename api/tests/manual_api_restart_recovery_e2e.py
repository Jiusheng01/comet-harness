from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import delete, select, text

import app.core.harness.runtime.agent_runtime as agent_runtime_module
from app.core.harness.checkpoint.models import HarnessCheckpoint
from app.core.harness.checkpoint.postgres_store import (
    PostgresCheckpointStore,
)
from app.core.harness.context import ContextManager
from app.core.harness.runtime.agent_runtime import AgentRuntime
from app.core.harness.runtime.contracts import (
    HarnessMessage,
    ModelStreamEvent,
    ModelTurn,
    ToolCall,
)
from app.core.realtime import bus
from app.db.postgres import SessionLocal
from app.models.conversation_model import (
    ROLE_ASSISTANT,
    ROLE_USER,
    Conversation,
    Message,
)
from app.models.harness_checkpoint_model import (
    HarnessCheckpointRecord,
)


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TOOL_RESULT = "2026-08-14 11:29:00"
EXPECTED_FINAL = (
    "API 重启恢复成功：2026-08-14 11:29:00。"
)


class FakeSpan:
    def set_payload(self, *args, **kwargs) -> None:
        pass

    def set_tokens(self, *args, **kwargs) -> None:
        pass


class FakeTracer:
    @asynccontextmanager
    async def llm_span(self, *args, **kwargs):
        yield FakeSpan()


class NoDuplicateToolExecutor:
    def __init__(self) -> None:
        self.call_count = 0

    async def execute(self, **kwargs):
        self.call_count += 1

        raise AssertionError(
            "恢复时不应该重新执行已经完成的工具"
        )


class ResumeModel:
    @property
    def model_name(self) -> str:
        return "fake-api-restart-resume-model"

    async def stream(self, messages, tools):
        tool_results = [
            message.content
            for message in messages
            if message.role == "tool"
        ]

        assert EXPECTED_TOOL_RESULT in tool_results

        yield ModelStreamEvent(
            type="completed",
            turn=ModelTurn(
                text=EXPECTED_FINAL
            ),
        )


async def seed_and_crash(
    user_id: uuid.UUID,
    conv_id: uuid.UUID,
    turn_id: uuid.UUID,
) -> None:
    """进程 A：

    写入真实业务输入 + PostgreSQL checkpoint，
    再创建 Redis lock/lease，最后 os._exit 模拟硬崩溃。

    os._exit 不执行 finally / atexit / graceful shutdown，
    更接近 kill -9 / Task Manager 强杀 API 进程。
    """

    # 测试里把 TTL 缩短，避免真的等待 60/120 秒。
    # Redis key 创建之后 TTL 已经固化，因此进程 B
    # 不需要修改生产配置。
    bus._LOCK_TTL = 3
    bus._EXECUTION_LEASE_TTL = 2

    async with SessionLocal() as session:
        session.add(
            Conversation(
                id=conv_id,
                user_id=user_id,
                title="Harness API Restart E2E",
            )
        )

        session.add(
            Message(
                id=turn_id,
                conversation_id=conv_id,
                role=ROLE_USER,
                content="测试 API 硬崩溃后的自动恢复",
                meta_data={
                    "attachments": [
                        {
                            "file_name": "restart.txt",
                            "text": (
                                "process crash recovery"
                            ),
                        }
                    ],
                    "image_keys": [],
                    "harness_request": {
                        "version": 1,
                        "skill_id": None,
                        "enable_knowledge": True,
                        "enable_memory": False,
                        "enable_web_search": False,
                    },
                },
            )
        )

        await session.commit()

    async with SessionLocal() as session:
        store = PostgresCheckpointStore(
            session,
            user_id,
        )

        await store.save(
            HarnessCheckpoint(
                checkpoint_id=turn_id,
                runtime="function_calling",
                next_iteration=1,
                messages=[
                    HarnessMessage(
                        role="user",
                        content=(
                            "测试 API 硬崩溃后的自动恢复"
                        ),
                    ),
                    HarnessMessage(
                        role="assistant",
                        content="",
                        tool_calls=[
                            ToolCall(
                                id="call_datetime_e2e",
                                name="datetime",
                                arguments={
                                    "query": (
                                        "current time"
                                    ),
                                },
                            )
                        ],
                    ),
                    HarnessMessage(
                        role="tool",
                        content=EXPECTED_TOOL_RESULT,
                        tool_call_id=(
                            "call_datetime_e2e"
                        ),
                    ),
                ],
                accumulated_text="",
                user_input=(
                    "测试 API 硬崩溃后的自动恢复"
                ),
                max_iterations=5,
                metadata={
                    "model_name": (
                        "fake-crashed-model"
                    ),
                },
            )
        )

    locked = await bus.acquire_turn_lock_strict(
        str(conv_id)
    )

    assert locked is True

    lease_ok = await bus.refresh_execution_lease(
        str(turn_id)
    )

    assert lease_ok is True

    # 模拟 API 进程被操作系统直接杀掉。
    # 不允许 finally 做任何清理。
    os._exit(23)


async def restart_api_process(
    user_id: uuid.UUID,
    conv_id: uuid.UUID,
    turn_id: uuid.UUID,
) -> None:
    """进程 B：

    真正进入 app.main.lifespan。
    lifespan 自动启动 CheckpointRecoveryWorker。

    为了让测试不调用真实 LLM，只替换恢复执行中的模型；
    checkpoint / worker / request rebuild / lifespan /
    PostgreSQL / Redis 全部使用真实实现。
    """

    # 避免 E2E 被 ES / Neo4j 初始化拖慢。
    # 它们与 Harness recovery 无关。
    import app.core.memory.graph_schema as graph_schema_module
    import app.core.rag.es_index as es_index_module

    async def noop_startup() -> None:
        return None

    es_index_module.ensure_index = (
        noop_startup
    )

    graph_schema_module.ensure_graph_schema = (
        noop_startup
    )

    import app.core.harness.recovery as recovery_module
    from app.main import create_app, lifespan
    from app.services.chat_service import ChatService

    # 生产默认扫描更慢。
    # E2E 缩短到 250ms，让测试几秒内结束。
    worker = (
        recovery_module.get_recovery_worker()
    )

    worker._scan_interval = 0.25

    original_get_tracer = (
        agent_runtime_module.get_tracer
    )

    agent_runtime_module.get_tracer = (
        lambda: FakeTracer()
    )

    async def recovered_chat_turn(
        self,
        recovered_user_id,
        recovered_conv_id,
        body,
        attachments,
        skip_user_message,
        recovered_turn_id,
    ) -> None:
        assert recovered_user_id == user_id
        assert recovered_conv_id == conv_id
        assert recovered_turn_id == turn_id
        assert skip_user_message is True

        # 证明 Recovery Worker 确实从
        # user message.meta_data 重建了请求。
        assert body.enable_knowledge is True
        assert body.enable_memory is False
        assert body.enable_web_search is False

        assert len(body.attachments) == 1
        assert (
            body.attachments[0].text
            == "process crash recovery"
        )

        executor = NoDuplicateToolExecutor()

        try:
            async with SessionLocal() as session:
                store = (
                    PostgresCheckpointStore(
                        session,
                        recovered_user_id,
                    )
                )

                runtime = AgentRuntime(
                    model=ResumeModel(),
                    tool_executor=executor,
                    model_tools=[],
                    context_manager=(
                        ContextManager()
                    ),
                    checkpoint_store=store,
                )

                final_text = ""

                async for event in runtime.resume(
                    recovered_turn_id,
                    cleanup_checkpoint_on_finish=False,
                ):
                    if (
                        event.get("type")
                        == "final"
                    ):
                        final_text = (
                            event.get("text")
                            or ""
                        )

                assert final_text == EXPECTED_FINAL

                # 已完成的 datetime 工具不能执行第二遍。
                assert executor.call_count == 0

                session.add(
                    Message(
                        conversation_id=(
                            recovered_conv_id
                        ),
                        role=ROLE_ASSISTANT,
                        content=final_text,
                        meta_data={
                            "turn_id": str(
                                recovered_turn_id
                            ),
                            "recovered_by": (
                                "api_restart_e2e"
                            ),
                        },
                    )
                )

                # 业务结果先 durable commit。
                await session.commit()

                # 再 ACK checkpoint。
                await store.delete(
                    recovered_turn_id
                )

        finally:
            await bus.clear_execution_lease(
                str(recovered_turn_id)
            )

            await bus.clear_stream_buffer(
                str(recovered_conv_id)
            )

            await bus.release_turn_lock(
                str(recovered_conv_id)
            )

    ChatService._run_chat_turn_bg = (
        recovered_chat_turn
    )

    app = create_app()

    try:
        async with lifespan(app):
            print(
                "fresh API process lifespan entered: True",
                flush=True,
            )

            deadline = (
                asyncio.get_running_loop().time()
                + 15
            )

            while (
                asyncio.get_running_loop().time()
                < deadline
            ):
                async with SessionLocal() as session:
                    checkpoint = await session.get(
                        HarnessCheckpointRecord,
                        turn_id,
                    )

                    result = await session.execute(
                        select(Message)
                        .where(
                            Message.conversation_id
                            == conv_id
                        )
                        .where(
                            Message.role
                            == ROLE_ASSISTANT
                        )
                    )

                    assistants = list(
                        result.scalars().all()
                    )

                    recovered = [
                        message
                        for message in assistants
                        if (
                            (
                                message.meta_data
                                or {}
                            ).get("turn_id")
                            == str(turn_id)
                        )
                    ]

                    if (
                        checkpoint is None
                        and len(recovered) == 1
                    ):
                        print(
                            "lifespan worker recovered checkpoint: True",
                            flush=True,
                        )

                        print(
                            "completed tool executed again: False",
                            flush=True,
                        )

                        return

                await asyncio.sleep(0.25)

            raise RuntimeError(
                "等待 lifespan Recovery Worker "
                "自动恢复超时"
            )

    finally:
        agent_runtime_module.get_tracer = (
            original_get_tracer
        )


async def first_user_id() -> uuid.UUID:
    async with SessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id FROM users "
                "ORDER BY created_at ASC "
                "LIMIT 1"
            )
        )

        user_id = result.scalar_one_or_none()

    if user_id is None:
        raise RuntimeError(
            "users 表为空，无法运行 E2E"
        )

    return user_id


async def checkpoint_exists(
    user_id: uuid.UUID,
    turn_id: uuid.UUID,
) -> bool:
    async with SessionLocal() as session:
        store = PostgresCheckpointStore(
            session,
            user_id,
        )

        return (
            await store.load(turn_id)
            is not None
        )


async def recovered_assistants(
    conv_id: uuid.UUID,
    turn_id: uuid.UUID,
) -> list[Message]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Message)
            .where(
                Message.conversation_id
                == conv_id
            )
            .where(
                Message.role
                == ROLE_ASSISTANT
            )
        )

        messages = list(
            result.scalars().all()
        )

        turn_text = str(turn_id)

        return [
            message
            for message in messages
            if (
                (
                    message.meta_data
                    or {}
                ).get("turn_id")
                == turn_text
            )
        ]


def child_env() -> dict[str, str]:
    env = os.environ.copy()

    existing = env.get(
        "PYTHONPATH",
        "",
    )

    env["PYTHONPATH"] = (
        str(ROOT)
        if not existing
        else (
            str(ROOT)
            + os.pathsep
            + existing
        )
    )

    return env


async def parent_main() -> None:
    user_id = await first_user_id()

    conv_id = uuid.uuid4()
    turn_id = uuid.uuid4()

    script = str(
        Path(__file__).resolve()
    )

    try:
        print(
            "phase 1: start API-like process and hard crash"
        )

        crashed = subprocess.run(
            [
                sys.executable,
                script,
                "seed-crash",
                str(user_id),
                str(conv_id),
                str(turn_id),
            ],
            cwd=str(ROOT),
            env=child_env(),
            check=False,
            timeout=30,
        )

        print(
            "crashed process exit code:",
            crashed.returncode,
        )

        assert crashed.returncode == 23

        survived = await checkpoint_exists(
            user_id,
            turn_id,
        )

        assert survived is True

        print(
            "checkpoint survived OS process crash:",
            survived,
        )

        lease_survived = (
            await bus.has_execution_lease(
                str(turn_id)
            )
        )

        print(
            "Redis lease survived crashed process:",
            lease_survived,
        )

        assert lease_survived is True

        print()
        print(
            "phase 2: start fresh API process"
        )

        restarted = subprocess.run(
            [
                sys.executable,
                script,
                "restart",
                str(user_id),
                str(conv_id),
                str(turn_id),
            ],
            cwd=str(ROOT),
            env=child_env(),
            check=False,
            timeout=45,
        )

        print(
            "fresh process exit code:",
            restarted.returncode,
        )

        assert restarted.returncode == 0

        still_exists = await checkpoint_exists(
            user_id,
            turn_id,
        )

        assert still_exists is False

        assistants = await recovered_assistants(
            conv_id,
            turn_id,
        )

        assert len(assistants) == 1
        assert (
            assistants[0].content
            == EXPECTED_FINAL
        )

        print(
            "assistant persisted after restart: True"
        )

        print(
            "checkpoint deleted after business ACK: True"
        )

        print(
            "duplicate recovered assistants:",
            len(assistants) - 1,
        )

        print()
        print(
            "API process restart recovery E2E passed."
        )

    finally:
        try:
            await bus.clear_execution_lease(
                str(turn_id)
            )

            await bus.clear_stream_buffer(
                str(conv_id)
            )

            await bus.release_turn_lock(
                str(conv_id)
            )

        except Exception:
            pass

        async with SessionLocal() as session:
            try:
                store = (
                    PostgresCheckpointStore(
                        session,
                        user_id,
                    )
                )

                await store.delete(
                    turn_id
                )

            except Exception:
                await session.rollback()

            await session.execute(
                delete(Conversation).where(
                    Conversation.id
                    == conv_id
                )
            )

            await session.commit()


def parse_uuid_arg(index: int) -> uuid.UUID:
    return uuid.UUID(
        sys.argv[index]
    )


if __name__ == "__main__":
    mode = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "parent"
    )

    if mode == "seed-crash":
        asyncio.run(
            seed_and_crash(
                parse_uuid_arg(2),
                parse_uuid_arg(3),
                parse_uuid_arg(4),
            )
        )

    elif mode == "restart":
        asyncio.run(
            restart_api_process(
                parse_uuid_arg(2),
                parse_uuid_arg(3),
                parse_uuid_arg(4),
            )
        )

    elif mode == "parent":
        asyncio.run(
            parent_main()
        )

    else:
        raise SystemExit(
            f"unknown mode: {mode}"
        )
