# Comet Harness 文档

> Comet Harness 的工程设计文档。以 Agent Runtime、真实 Agent Workloads、RAG / Memory、可观测、评测与部署为主。

## 核心入口

- [HARNESS_ARCHITECTURE.md](HARNESS_ARCHITECTURE.md) — Agent Harness / Runtime 总体架构、Checkpoint / Resume、Crash Recovery 与 Durable ACK
- [01-LLM应用工程](01-LLM应用工程/) — 模型适配、SSE、ASR 与基础设施
- [02-RAG知识库](02-RAG知识库/) — 分块、混合检索、Rerank、引用、多模态
- [03-Agent核心](03-Agent核心/) — Function Calling / ReAct、Tool Runtime、MCP、Verifier Loop
- [04-记忆](04-记忆/) — 长期记忆、Neo4j、召回、反馈闭环
- [05-Agent工作负载](05-Agent工作负载/) — Deep Research 与定时任务等复杂 Agent Workloads
- [06-工程化与部署](06-工程化与部署/) — 安全、Celery、分享、推送、部署与 Observability
- [07-情绪与个性化](07-情绪与个性化/) — Personal AI 产品能力
- [08-评测体系](08-评测体系/) — 离线评测、公共 Benchmark 与回归验证
- [release-notes](release-notes/) — 历史版本发布说明

## 文档原则

- 当前源码与 `HARNESS_ARCHITECTURE.md` 是 Harness 行为的主要事实来源。
- 产品能力作为 Harness 的真实 workload 保留，而不是替代 Runtime 主线。
- 已退休功能不继续保留在当前设计文档中；数据库历史由 Alembic migration 保留。
- 新增 Harness 能力应同步补充架构、恢复边界、测试与可观测说明。
