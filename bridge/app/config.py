from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bridge_service_token: str = Field(min_length=24)
    chatwoot_webhook_token: str = Field(min_length=24)
    frontend_url: str = "http://localhost:3000"
    chatwoot_api_url: str = "http://rails:3000"
    chatwoot_account_id: int = 1
    chatwoot_api_token: str = ""
    chatwoot_inbox_id: int = 1
    chatwoot_agent_bot_id: int = 0
    chatwoot_inbox_identifier: str = ""
    chatwoot_inbox_hmac_token: str = ""
    chatwoot_team_support_id: int = 0
    chatwoot_team_financial_id: int = 0
    chatwoot_team_commercial_id: int = 0
    orbycore_api_url: str = "http://host.docker.internal:8000"
    orbycore_portal_url: str = "http://host.docker.internal:5173/portal"
    orbycore_service_token: str = ""
    mobile_session_hmac_secret: str = Field(default="", min_length=32)
    mobile_session_issuer: str = "orbycore-chatwoot-bridge"
    mobile_session_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    redis_url: str = "redis://:change-me@bridge-redis:6379/0"
    automation_enabled: bool = True
    automation_trigger_prefix: str = "/"
    request_timeout_seconds: float = 12.0
    webhook_max_attempts: int = Field(default=5, ge=1, le=20)
    webhook_max_backoff_seconds: int = Field(default=30, ge=1, le=300)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
