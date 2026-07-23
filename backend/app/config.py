from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str

    llm_provider: str = "bedrock"
    embedding_provider: str = "bedrock"

    aws_region: str = "us-east-1"
    bedrock_model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 2048

    cockroach_mcp_url: str = ""
    cockroach_mcp_api_key: str = ""
    cockroach_mcp_cluster_id: str = ""

    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    embedding_dims: int = 1024
    recall_candidates: int = 20
    recall_top_k: int = 5
    w_quality: float = 0.15
    w_age: float = 0.10
    feedback_up: float = 0.10
    feedback_down: float = 0.15
    agent_max_turns: int = 6

    mock_seed: int | None = None


settings = Settings()
