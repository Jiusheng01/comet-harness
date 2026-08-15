"""记忆图谱的节点与边模型（Neo4j 写入用的内存数据结构）。

采用四层溯源结构，完整保留「记忆从哪段对话、哪个片段、哪句话来」：

    Dialogue（来源：一次对话 / 一段主动记住的文本）
      └─(:HAS_CHUNK)→ Chunk（按轮次 / token 切分的片段）
            └─(:HAS_STATEMENT)→ Statement（原子陈述句，带类型与时间属性）
                  └─(:MENTIONS)→ Entity（萃取出的实体）

在此之上构建语义层：

    Entity ─(:RELATION{predicate,...})→ Entity   实体间三元组关系
    Event  ─(:INVOLVES{role})→ Entity             事件涉及的实体（带 event_time，供时间线）
    Entity ─(:IN_COMMUNITY)→ Community            社区聚类（阶段7 使用）

所有节点 / 边都带 user_id 做多租户隔离；按业务键 MERGE 幂等写入。
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ── 节点标签 ──
LABEL_DIALOGUE = "Dialogue"
LABEL_CHUNK = "Chunk"
LABEL_STATEMENT = "Statement"
LABEL_ENTITY = "Entity"
LABEL_EVENT = "Event"
LABEL_COMMUNITY = "Community"
LABEL_INSIGHT = "Insight"

# ── 关系类型 ──
REL_HAS_CHUNK = "HAS_CHUNK"
REL_HAS_STATEMENT = "HAS_STATEMENT"
REL_MENTIONS = "MENTIONS"
REL_RELATION = "RELATION"
REL_INVOLVES = "INVOLVES"
REL_IN_COMMUNITY = "IN_COMMUNITY"
REL_DERIVED_FROM = "DERIVED_FROM"

# ── 记忆来源 ──
SOURCE_AUTO = "auto"
SOURCE_MANUAL = "manual"

# ── 陈述类型 / 时间类型 ──
STMT_FACT = "FACT"
STMT_OPINION = "OPINION"
STMT_PREDICTION = "PREDICTION"
STMT_SUGGESTION = "SUGGESTION"

TEMPORAL_STATIC = "STATIC"
TEMPORAL_DYNAMIC = "DYNAMIC"
TEMPORAL_ATEMPORAL = "ATEMPORAL"

# ── 记忆层级 ──
LAYER_SHORT_TERM = "short_term"
LAYER_LONG_TERM = "long_term"

# ── 连接强度 ──
CONNECT_STRONG = "strong"
CONNECT_WEAK = "weak"


def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now()


class DialogueNode(BaseModel):
    """一次萃取的来源根节点：一段对话或一条主动记住的文本。"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_new_id)
    user_id: str
    content: str
    source: str = SOURCE_MANUAL
    source_message_id: str | None = None
    dialog_at: datetime = Field(default_factory=_now)
    created_at: datetime = Field(default_factory=_now)


class ChunkNode(BaseModel):
    """对话片段：按轮次 / token 切分，承上启下用于溯源。"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_new_id)
    user_id: str
    dialog_id: str
    content: str
    speaker: str | None = None
    sequence: int = 0
    created_at: datetime = Field(default_factory=_now)


class StatementNode(BaseModel):
    """原子陈述句：萃取的最小语义单元，带类型与时间属性。"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_new_id)
    user_id: str
    chunk_id: str
    statement: str
    stmt_type: str = STMT_FACT
    temporal_type: str = TEMPORAL_STATIC
    speaker: str | None = None
    valid_at: datetime | None = None
    invalid_at: datetime | None = None
    dialog_at: datetime | None = None
    embedding: list[float] | None = None
    importance: float = 0.5
    confidence: float = 0.8
    memory_layer: str = LAYER_SHORT_TERM
    access_count: int = 0
    last_access_at: datetime | None = None
    # 记忆图谱中的情绪语义元数据，仅用于陈述检索/画像
    has_emotional_state: bool = False
    emotion_type: str | None = None
    emotion_intensity: float | None = None
    emotion_keywords: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)


class EntityNode(BaseModel):
    """实体节点：萃取出的画像实体（人/组织/知识/偏好/目标等）。"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_new_id)
    user_id: str
    name: str
    type: str
    description: str = ""
    aliases: list[str] = Field(default_factory=list)
    name_embedding: list[float] | None = None
    community_id: str | None = None
    importance: float = 0.5
    confidence: float = 0.8
    memory_layer: str = LAYER_SHORT_TERM
    access_count: int = 0
    last_access_at: datetime | None = None
    mention_count: int = 1
    connect_strength: str = CONNECT_STRONG
    core_facts: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
    last_consolidated_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)


class EventNode(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_new_id)
    user_id: str
    title: str
    description: str = ""
    event_time: datetime | None = None
    embedding: list[float] | None = None
    created_at: datetime = Field(default_factory=_now)


class CommunityNode(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_new_id)
    user_id: str
    name: str
    summary: str = ""
    member_count: int = 0
    created_at: datetime = Field(default_factory=_now)


class InsightNode(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_new_id)
    user_id: str
    theme: str
    content: str
    embedding: list[float] | None = None
    importance: float = 0.6
    confidence: float = 0.7
    source_count: int = 0
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class DerivedFromEdge(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    insight_id: str
    entity_id: str
    created_at: datetime = Field(default_factory=_now)


class RelationEdge(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_new_id)
    user_id: str
    source_id: str
    target_id: str
    predicate: str
    predicate_surface: str = ""
    source_text: str = ""
    statement_id: str | None = None
    value: str | None = None
    valid_at: datetime | None = None
    invalid_at: datetime | None = None
    importance: float = 0.5
    confidence: float = 0.8
    access_count: int = 0
    created_at: datetime = Field(default_factory=_now)


class MentionEdge(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    statement_id: str
    entity_id: str
    connect_strength: str = "strong"
    created_at: datetime = Field(default_factory=_now)


class InvolvesEdge(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    event_id: str
    entity_id: str
    role: str = ""
    created_at: datetime = Field(default_factory=_now)


__all__ = [
    "LABEL_DIALOGUE", "LABEL_CHUNK", "LABEL_STATEMENT", "LABEL_ENTITY",
    "LABEL_EVENT", "LABEL_COMMUNITY", "LABEL_INSIGHT",
    "REL_HAS_CHUNK", "REL_HAS_STATEMENT", "REL_MENTIONS", "REL_RELATION",
    "REL_INVOLVES", "REL_IN_COMMUNITY", "REL_DERIVED_FROM",
    "SOURCE_AUTO", "SOURCE_MANUAL", "STMT_FACT", "STMT_OPINION",
    "STMT_PREDICTION", "STMT_SUGGESTION", "TEMPORAL_STATIC",
    "TEMPORAL_DYNAMIC", "TEMPORAL_ATEMPORAL", "LAYER_SHORT_TERM",
    "LAYER_LONG_TERM", "CONNECT_STRONG", "CONNECT_WEAK",
    "DialogueNode", "ChunkNode", "StatementNode", "EntityNode",
    "EventNode", "CommunityNode", "InsightNode", "RelationEdge",
    "MentionEdge", "InvolvesEdge", "DerivedFromEdge",
]
