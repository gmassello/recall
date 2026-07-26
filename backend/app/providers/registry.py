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
    if settings.llm_provider == "gemini":
        from app.providers.gemini_provider import GeminiProvider

        return GeminiProvider()
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")


@lru_cache(maxsize=1)
def get_embedder() -> EmbeddingProvider:
    if settings.embedding_provider == "bedrock":
        from app.providers.bedrock import BedrockTitanEmbedder

        return BedrockTitanEmbedder()
    if settings.embedding_provider == "gemini":
        from app.providers.gemini_provider import GeminiEmbedder

        return GeminiEmbedder()
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {settings.embedding_provider}")
