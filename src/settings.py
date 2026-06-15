from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    xai_api_key: str = ""
    xai_model: str = "grok-voice-latest"
    openai_api_key: str = ""
    openai_model: str = "gpt-realtime"
    openai_chat_model: str = "gpt-4o-mini"
    xai_chat_model: str = "grok-4.3"
    proxy_master_secret: str = ""
    port: int = 8081
    host: str = "0.0.0.0"
    log_level: str = "info"
    log_audio: bool = False
    kb_inject_max_points_per_side: int = 30
    kb_data_dir: str = "knowledge_base"
    kb_audit_log_dir: str = ""

    @property
    def xai_upstream_url(self) -> str:
        return f"wss://api.x.ai/v1/realtime?model={self.xai_model}"


settings = Settings()
