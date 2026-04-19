from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent.parent / ".env"),
        case_sensitive=False
    )
    google_credentials_path: str
    google_token_path: str
    database_url: str
    app_env: str = "development"
    log_level: str = "INFO"
    confidence_auto_act: float = 0.85
    confidence_human_review: float = 0.60
    llm_api_key: str
    llm_provider: str
    llm_model: str
    llm_temperature: float 


def _load_settings() -> Settings:
    # BaseSettings resolves required fields from env sources at runtime.
    return Settings()  # pyright: ignore[reportCallIssue]


settings = _load_settings()



