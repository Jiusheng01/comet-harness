"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.controllers.router import api_router
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.request_context import RequestContextMiddleware
from app.db import elastic, neo4j, postgres, redis

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.db.migrate import upgrade_to_head

    try:
        await upgrade_to_head()
    except Exception as e:
        logger.error("数据库自动迁移失败，请检查迁移脚本或手动执行 alembic upgrade head: %s", e)

    from app.core.rag.es_index import ensure_index

    try:
        await ensure_index()
    except Exception as e:
        logger.warning("ES 索引初始化失败（稍后可重试）: %s", e)

    from app.core.memory.graph_schema import ensure_graph_schema

    try:
        await ensure_graph_schema()
    except Exception as e:
        logger.warning("记忆图谱 schema 初始化失败（稍后可重试）: %s", e)

    from app.core.agent.tracing.span_recorder import get_recorder

    try:
        await get_recorder().start()
    except Exception as e:
        logger.warning("Tracing 落库器启动失败（稍后可重试）: %s", e)

    from app.core.harness.recovery import get_recovery_worker

    try:
        await get_recovery_worker().start()
    except Exception as e:
        logger.warning("Harness checkpoint 恢复器启动失败（稍后可手动恢复）: %s", e)

    logger.info("%s 启动完成", settings.app_name)
    yield

    try:
        await get_recovery_worker().stop()
    except Exception as e:
        logger.warning("Harness checkpoint 恢复器关闭异常: %s", e)

    try:
        await get_recorder().stop()
    except Exception as e:
        logger.warning("Tracing 落库器关闭异常: %s", e)

    await postgres.close()
    await elastic.close()
    await neo4j.close()
    await redis.close()
    logger.info("%s 已关闭，连接池释放完成", settings.app_name)


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} API",
        description="Comet Harness — Durable Agent Runtime with RAG, Memory and Research workloads",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
