"""应用配置：全部从环境变量 / .env 读取，不硬编码。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 应用
    app_name: str = "Comet"
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    # 安全
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080
    refresh_token_expire_days: int = 30
    fernet_key: str = "change-me-fernet-key"

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "comet"
    postgres_password: str = "comet"
    postgres_db: str = "comet"

    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_pool_pre_ping: bool = True
    db_statement_timeout_ms: int = 60000

    # Elasticsearch
    es_host: str = "http://localhost:9200"
    es_username: str = ""
    es_password: str = ""
    es_max_retries: int = 3
    es_request_timeout: int = 30
    es_max_connections: int = 25

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "cometneo4j"
    neo4j_max_pool_size: int = 50
    neo4j_connection_timeout: int = 30

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 50
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # RAG
    embedding_dims: int = 1024
    global_search_min_vector_score: float = 0.45
    memory_search_min_vector_score: float = 0.45

    # Memory
    consolidate_min_access: int = 2
    consolidate_min_importance: float = 0.7
    consolidate_min_mention: int = 3
    consolidate_min_age_hours: int = 24
    consolidate_profile_top_k: int = 5

    reflection_top_k: int = 25
    reflection_stmt_per_entity: int = 4
    reflection_min_insights: int = 3
    reflection_max_insights: int = 6
    reflection_min_entities: int = 5
    reflection_trigger_threshold: int = 20

    active_recall_entity_top_k: int = 5
    active_recall_insight_top_k: int = 2
    active_recall_min_score: float = 0.5
    active_recall_min_confidence: float = 0.6
    active_recall_uncertain_confidence: float = 0.75
    active_recall_max_chars: int = 600

    cross_session_max_convs: int = 3
    cross_session_turns_per_conv: int = 4
    cross_session_max_chars: int = 1200

    # Research
    research_max_queries: int = 8
    research_search_top_k: int = 8
    research_search_concurrency: int = 2
    research_search_retries: int = 3
    research_fetch_top_n: int = 8
    research_fetch_concurrency: int = 4
    research_fetch_timeout: int = 12
    research_source_truncate_chars: int = 3000

    # Tracing
    tracing_enabled: bool = True
    tracing_sample_rate: float = 1.0
    tracing_batch_size: int = 20
    tracing_flush_interval: float = 2.0
    tracing_queue_maxsize: int = 5000

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
