from functools import lru_cache

from app.config import settings
from app.providers.base import EmbeddingProvider, LLMProvider


@lru_cache(maxsize=1)
def get_llm() -> LLMProvider:
    if settings.llm_provider == "bedrock":
        from app.providers.bedrock import BedrockClaudeProvider

        return BedrockClaudeProvider()
    if settings.llm_provider == "anthropic":
        from app.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    raise ValueError(f"LLM_PROVIDER desconocido: {settings.llm_provider}")


@lru_cache(maxsize=1)
def get_embedder() -> EmbeddingProvider:
    if settings.embedding_provider == "bedrock":
        from app.providers.bedrock import BedrockTitanEmbedder

        return BedrockTitanEmbedder()
    raise ValueError(f"EMBEDDING_PROVIDER desconocido: {settings.embedding_provider}")
