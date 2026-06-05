from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    xai_api_key: str = ""
    xai_model: str = "grok-voice-latest"
    proxy_auth_token: str = ""
    port: int = 8081
    host: str = "0.0.0.0"
    log_level: str = "info"
    log_audio: bool = False

    @property
    def xai_upstream_url(self) -> str:
        return f"wss://api.x.ai/v1/realtime?model={self.xai_model}"


settings = Settings()
