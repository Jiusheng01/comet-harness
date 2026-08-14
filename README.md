# Comet Harness

> **Durable Agent Runtime for real-world AI applications.**  
> 自主管理 Agent 执行循环、工具调用、上下文预算、Checkpoint / Resume、进程崩溃恢复与执行观测。

Comet Harness 是一个面向真实 AI 应用的 **Agent Harness / Runtime**。项目把 Agent 的执行控制从框架内部抽离出来，由自身 Runtime 管理 Function Calling / ReAct 多轮循环、统一 Tool Runtime、Context Budget、Durable Checkpoint、Crash Recovery 与 Trace。

RAG、长期记忆、联网搜索、MCP、Deep Research 等能力继续作为真实业务场景存在，用来验证 Runtime 不只是一个抽象 Demo，而能够承载完整 AI 产品工作负载。

> **项目来源：**本仓库基于公开项目 [lm041520/Comet](https://github.com/lm041520/Comet) 继续演进。原项目已有的 RAG、Memory、搜索、Deep Research 等产品能力予以保留；本仓库当前重点是 Agent execution infrastructure 的重构与增强。

---

## Architecture

README 不再使用复杂 Mermaid，下面按“工作负载 → Runtime → Durable State”的层次展示核心关系：

```text
┌──────────────────────────── AI Workloads ────────────────────────────┐
│        Chat        RAG / Knowledge        Memory        Research     │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                         FastAPI / Service
                                │
                        Agent Orchestrator
                                │
                 ┌──────────────┴──────────────┐
                 │                             │
        ┌────────▼────────┐           ┌────────▼────────┐
        │  AgentRuntime   │           │  ReactRuntime   │
        │ Function Calling│           │ ReAct fallback  │
        └────────┬────────┘           └────────┬────────┘
                 └──────────────┬──────────────┘
                                │
        ┌───────────────────────┼────────────────────────┐
        │                       │                        │
┌───────▼────────┐    ┌─────────▼────────┐     ┌────────▼────────┐
│  ModelAdapter  │    │ ContextManager   │     │  ToolExecutor   │
│ model boundary │    │ budget/compaction│     │ unified tools   │
└────────────────┘    └──────────────────┘     └────────┬────────┘
                                                       │
                                      ┌────────────────┼───────────────┐
                                      │                │               │
                                     RAG             Memory        Web / MCP

                         Durable Execution Layer
                                │
                    ┌───────────┴───────────┐
                    │                       │
             ┌──────▼──────┐         ┌──────▼──────┐
             │ PostgreSQL  │         │    Redis    │
             │ Checkpoint  │         │ lease/lock  │
             └──────┬──────┘         └──────┬──────┘
                    └───────────┬───────────┘
                                │
                    CheckpointRecoveryWorker
                                │
                         Runtime.resume()

Observability: Trace / Span covers Runtime, LLM, Context and Tool execution.
```

完整设计与恢复语义见 **[`docs/HARNESS_ARCHITECTURE.md`](docs/HARNESS_ARCHITECTURE.md)**。

---

## Agent Harness / Runtime

LangChain 仍用于模型与工具生态适配，但 Agent Loop 的控制权进入项目自身 Runtime。

| 能力 | 当前实现 |
|---|---|
| **Agent Runtime** | `AgentRuntime` 驱动原生 Function Calling 多轮循环 |
| **ReAct Runtime** | `ReactRuntime` 解析 Action / Observation，作为弱模型降级路径 |
| **Model Boundary** | `ModelAdapter` 隔离具体模型 / LangChain Message 类型 |
| **Tool Runtime** | Function Calling / ReAct 共用 `ToolExecutor` |
| **Context Management** | Token Budget、Compaction、超长 Tool Result 截断、Tool Call / Result 原子块保护 |
| **Durable State** | `CheckpointStore` Protocol + PostgreSQL 持久化 |
| **Resume** | 从 Harness Messages 与 `next_iteration` 恢复执行，而不是从头重放 |
| **Crash Recovery** | Redis execution lease + strict conversation lock + Recovery Worker |
| **Durable ACK** | assistant 业务结果提交后才 ACK / 删除 checkpoint |
| **Observability** | LLM、Tool、Context 的 Trace / Span 与执行轨迹 |

### Durable execution semantics

正常完成：

```text
Runtime completion
      ↓
checkpoint retained
      ↓
assistant durable COMMIT
      ↓
business ACK
      ↓
checkpoint delete
```

进程硬崩溃：

```text
checkpoint survives in PostgreSQL
      ↓
old Redis execution lease expires
      ↓
new API process scans checkpoint
      ↓
strict conversation lock
      ↓
Runtime.resume()
      ↓
assistant durable COMMIT
      ↓
checkpoint ACK
```

当前可以准确描述的保证是：

```text
checkpoint-level durable execution
+ cross-process crash recovery
+ completed tool-batch replay protection
+ durable business ACK
+ execution tracing
```

> **边界说明：**当前不宣称 generic exactly-once tool execution。若外部 Tool 的副作用已经成功，但进程在 Tool Result / Checkpoint 持久化之前崩溃，仍需要后续 Tool Execution Journal、stable operation identity 与 idempotency policy 来处理该 operation-level crash window。

---

## Real-world Workloads

Harness 不是孤立运行时，仓库保留了一组完整业务能力作为真实工作负载：

| Workload | 作用 |
|---|---|
| **Chat** | Harness 的主要在线 workload，Runtime 自主执行模型与工具循环 |
| **RAG / Knowledge** | 文档、网页、图片入库；ES 向量 + BM25 混合检索；引用溯源 |
| **Memory** | 对话记忆萃取、Neo4j 图谱、主动召回、事件时间线与人类反馈 |
| **Web / MCP Tools** | 作为统一 Tool Runtime 可调度能力接入 Agent Loop |
| **Deep Research** | 多阶段研究流水线：规划、检索、提炼、反思、写作、Verifier |
| **Scheduled Tasks** | Celery 驱动定时研究、回顾、聚类与通知 |
| **Observability / Eval** | Trace、成本、Verifier、离线评测与恢复回归验证 |

产品侧仍包含多知识库、角色 / Skills、全局搜索、收藏、知识图谱、真人对话模式、分享与导出等能力，但 README 不再按版本堆叠功能清单；详细设计统一放在 [`docs/`](docs/) 与 [`docs/release-notes/`](docs/release-notes/) 中。

---

## Tech Stack

| Layer | Stack |
|---|---|
| Frontend | React 18 + TypeScript + Ant Design 5 + Vite + Zustand |
| Visualization | AntV X6 + ECharts |
| API | FastAPI + Pydantic + async SQLAlchemy |
| Agent Runtime | Self-owned Harness Runtime + LangChain Model / Tool Adapter |
| Business DB | PostgreSQL 16 + Alembic |
| Retrieval | Elasticsearch 8.17 + vector search + BM25 + IK tokenizer |
| Memory Graph | Neo4j 5.26 |
| Async / Coordination | Celery + Redis |
| Python Tooling | Python 3.12+ + uv |

---

## Development Topology

开发期推荐：**四个存储使用 Docker，应用进程在本机运行**，方便热重载和调试。

```text
Browser
  │
  ▼
web :5173
  │ /api proxy
  ▼
FastAPI :8000
  │
  ├── PostgreSQL :5432      business data + Harness checkpoint
  ├── Elasticsearch :9200   vector / BM25 retrieval
  ├── Neo4j :7474 / :7687   memory graph
  └── Redis :6379            Celery + execution lease / lock

Celery worker ── parse / memory / beat / research
Celery beat   ── scheduled jobs
```

---

## Requirements

| Software | Version | Usage |
|---|---|---|
| Docker Desktop | current | PostgreSQL / Elasticsearch / Neo4j / Redis |
| Python | 3.12+ | backend |
| uv | 0.5+ | Python dependency management |
| Node.js | 18+ | frontend |
| LLM API | — | at least one chat model and one embedding model |

默认端口：PostgreSQL `5432`、Elasticsearch `9200`、Neo4j `7474/7687`、Redis `6379`、API `8000`、Web `5173`。

---

## Quick Start

以下以 Windows PowerShell 为例。Linux / macOS 将 `Copy-Item` 换成 `cp`，Celery worker 通常可以去掉 `--pool=solo`。

### 1. Clone

```powershell
git clone https://github.com/Jiusheng01/comet-harness.git; cd comet-harness
```

### 2. Start storage services

```powershell
Copy-Item .env.example .env; docker compose build elasticsearch; docker compose up -d postgres elasticsearch neo4j redis
```

检查状态：

```powershell
docker compose ps
```

Elasticsearch 使用仓库中的自定义镜像并内置 IK 中文分词，因此首次启动前需要执行 `docker compose build elasticsearch`。

### 3. Install and configure backend

```powershell
cd api; uv python install 3.12; uv sync; Copy-Item .env.example .env
```

编辑 `api/.env`，至少生成并填写：

```powershell
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
```

将结果填入：

```dotenv
JWT_SECRET=your-random-secret
```

生成 Fernet Key：

```powershell
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

将结果填入：

```dotenv
FERNET_KEY=your-fernet-key
```

迁移数据库并启动 API：

```powershell
uv run alembic upgrade head; uv run python run.py
```

验证存储健康状态：

```powershell
Invoke-RestMethod http://localhost:8000/api/health
```

### 4. Start Celery worker

新开 PowerShell，在仓库根目录执行：

```powershell
cd api; uv run celery -A app.celery_app.celery_app worker -l info -Q default,parse,memory,beat,research --pool=solo
```

需要定时任务时，再开一个终端：

```powershell
cd api; uv run celery -A app.celery_app.celery_app beat -l info
```

### 5. Start frontend

新开 PowerShell：

```powershell
cd web; npm install; npm run dev
```

访问 `http://localhost:5173`。

### 6. Configure models

登录后进入 **设置 → 模型配置**：

- 必需：至少一个 **Chat Model** 与一个 **Embedding Model**。
- 强模型建议启用 `function_call` 能力，走原生 Function Calling Runtime。
- 可选：Web Search、Multimodal、Rerank 等模型能力。
- 每个模型保存后先执行连接测试，再设为默认。

---

## Harness Recovery Verification

`api/tests` 中保留了 Harness durable execution / recovery 的回归与跨进程 E2E 检查。

在 `api` 目录中可执行：

```powershell
uv run python tests\manual_checkpoint_resume_check.py
uv run python tests\manual_react_checkpoint_resume_check.py
uv run python tests\manual_postgres_runtime_resume_check.py
uv run python tests\manual_checkpoint_ack_check.py
uv run python tests\manual_checkpoint_recovery_worker_check.py
uv run python tests\manual_api_restart_recovery_e2e.py
```

跨进程 E2E 使用真实 PostgreSQL / Redis、新 Python/API 进程与 FastAPI lifespan / Recovery Worker；模型侧使用 deterministic fake model，因此测试重点是 Harness 的 durable execution 与 process recovery，而不是外部模型 Provider 的在线稳定性。

---

## Repository Layout

```text
comet-harness/
├── api/
│   ├── app/
│   │   ├── controllers/        # FastAPI routing
│   │   ├── services/           # business services
│   │   ├── repositories/       # persistence layer
│   │   ├── models/             # SQLAlchemy models
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── core/
│   │   │   ├── harness/        # Runtime / Context / Tools / Checkpoint / Recovery
│   │   │   ├── agent/          # agent integration / tool registry / prompts
│   │   │   ├── rag/            # parsing / chunking / retrieval
│   │   │   ├── memory/         # extraction / retrieval / clustering
│   │   │   ├── llm/            # model clients / factories
│   │   │   └── storage/        # file storage
│   │   ├── tasks/              # Celery tasks
│   │   └── db/                 # PostgreSQL / ES / Neo4j / Redis
│   ├── migrations/             # Alembic migrations
│   ├── tests/                  # Harness and business regression checks
│   └── pyproject.toml
├── web/                        # React frontend
├── docs/
│   ├── HARNESS_ARCHITECTURE.md
│   ├── 01-LLM应用工程/
│   ├── 02-RAG知识库/
│   ├── 03-Agent核心/
│   ├── 04-记忆/
│   ├── 05-Agent工作负载/
│   ├── 06-工程化与部署/
│   ├── 07-情绪与个性化/
│   ├── 08-评测体系/
│   └── release-notes/
├── docker/es/                  # Elasticsearch + IK image
├── docker-compose.yml
└── .env.example
```

---

## Documentation

- **Harness architecture:** [`docs/HARNESS_ARCHITECTURE.md`](docs/HARNESS_ARCHITECTURE.md)
- **Documentation index:** [`docs/README.md`](docs/README.md)
- **Release notes:** [`docs/release-notes/`](docs/release-notes/)

---

## Roadmap

```text
Completed
  ✓ AgentRuntime / ReactRuntime
  ✓ ModelAdapter
  ✓ Unified ToolExecutor
  ✓ Context Budget / Compaction
  ✓ PostgreSQL Checkpoint / Resume
  ✓ Durable ACK Boundary
  ✓ Redis Execution Lease / Conversation Lock
  ✓ Cross-process Recovery Worker / E2E
  ✓ Trace / Trajectory

Next
  → Unified Harness Regression Runner
  → Harness Eval / Benchmark
  → Stable Execution Identity
  → Tool Execution Journal
  → Operation-level Recovery Policy
```

---

## Development Conventions

- Python dependencies use **uv**; do not manage project dependencies with plain `pip`.
- Backend dependency direction: `controller → service → repository → model/db`.
- Database changes go through Alembic migrations; historical migrations are preserved.
- Business tables use `user_id` for tenant isolation; sensitive API credentials are encrypted before persistence.
- Before committing backend changes, run `uv run ruff check .` where applicable.
- Before committing frontend changes, run `npx tsc --noEmit` and the production build where applicable.

---

## Attribution

Comet Harness is evolved from the open-source project **[lm041520/Comet](https://github.com/lm041520/Comet)**.

The existing product features inherited from upstream and the Harness-specific execution infrastructure added in this repository are intentionally distinguished in the documentation. The current Harness work focuses on Runtime ownership, Tool Runtime, Context Management, Checkpoint / Resume, Crash Recovery, Durable ACK and Observability.
