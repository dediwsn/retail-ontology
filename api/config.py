"""
Runtime configuration. All values come from env vars set by the ECS task
definition (compute-stack.ts). Validated via Pydantic Settings at startup
so misconfiguration fails fast.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # AWS
    aws_region: str = Field(default="ap-northeast-2", alias="AWS_REGION")

    # Aurora (secret fetched at startup via boto3 — see compute-stack.ts comment)
    aurora_secret_arn: str = Field(alias="AURORA_SECRET_ARN")
    aurora_database_name: str = Field(default="ontology", alias="AURORA_DATABASE_NAME")

    # Neptune
    neptune_endpoint: str = Field(alias="NEPTUNE_ENDPOINT")
    neptune_port: int = Field(default=8182, alias="NEPTUNE_PORT")

    # OpenSearch Serverless
    opensearch_endpoint: str = Field(alias="OPENSEARCH_ENDPOINT")
    opensearch_index: str = Field(alias="OPENSEARCH_INDEX")

    # Bedrock
    bedrock_kb_id: str = Field(alias="BEDROCK_KB_ID")
    bedrock_guardrail_id: str = Field(alias="BEDROCK_GUARDRAIL_ID")
    bedrock_guardrail_version: str = Field(alias="BEDROCK_GUARDRAIL_VERSION")
    bedrock_reranker_inference_profile_arn: Optional[str] = Field(
        default=None, alias="BEDROCK_RERANKER_INFERENCE_PROFILE_ARN",
    )

    # AgentCore
    agentcore_memory_id: str = Field(alias="AGENTCORE_MEMORY_ID")

    # Models
    bedrock_chat_model_id: str = Field(
        default="global.anthropic.claude-sonnet-4-6", alias="BEDROCK_CHAT_MODEL_ID",
    )
    bedrock_chat_model_id_lite: str = Field(
        default="apac.anthropic.claude-haiku-4-5-v1:0", alias="BEDROCK_CHAT_MODEL_ID_LITE",
    )
    bedrock_embed_model_id: str = Field(
        # cohere.embed-multilingual-v3 was deprecated/unavailable in ap-northeast-2;
        # global.cohere.embed-v4:0 is the cross-region inference profile (1536-dim).
        default="global.cohere.embed-v4:0", alias="BEDROCK_EMBED_MODEL_ID",
    )
    bedrock_embed_dim: int = 1536

    # Buckets
    raw_docs_bucket: str = Field(alias="RAW_DOCS_BUCKET")
    uploads_bucket: str = Field(alias="UPLOADS_BUCKET")

    # App
    cors_allow_origins: str = Field(default="*", alias="CORS_ALLOW_ORIGINS")
    request_timeout_seconds: int = Field(default=60, alias="REQUEST_TIMEOUT_SECONDS")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
