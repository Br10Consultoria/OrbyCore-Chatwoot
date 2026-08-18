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
    chatwoot_inbox_identifier: str = ""
    chatwoot_inbox_hmac_token: str = ""
    orbycore_api_url: str = "http://host.docker.internal:8000"
    orbycore_portal_url: str = "http://host.docker.internal:5173/portal"
    orbycore_service_token: str = ""
    redis_url: str = "redis://:change-me@bridge-redis:6379/0"
    automation_enabled: bool = True
    automation_trigger_prefix: str = "/"
    request_timeout_seconds: float = 12.0
    log_level: str = "INFO"



@lru_cache
def get_settings() -> Settings:
    return Settings()
