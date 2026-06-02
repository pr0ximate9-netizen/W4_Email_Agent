"""
중앙 집중형 구성 설정입니다. 
애플리케이션 시작 시 한 번 로드됩니다.
값은 환경 변수 또는 .env 파일에서 읽어옵니다.

"""

from __future__ import annotations
import os
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # OpenAI
    openai_api_key: str = Field(default="sk-dummy-key", alias="OPENAI_API_KEY")
    openai_model:   str = Field(default="gpt-4o-mini",  alias="OPENAI_MODEL")
    openai_timeout: int = Field(default=30,             alias="OPENAI_TIMEOUT")
    openai_max_retries: int = Field(default=3,          alias="OPENAI_MAX_RETRIES")

    # Database
    db_path: str = Field(default="email_assistant.db", alias="DB_PATH")

    # Email source
    email_source:   str = Field(default="dummy",       alias="EMAIL_SOURCE")   # dummy | gmail
    dummy_data_path: str = Field(default="data/dummy_emails.json",
                                 alias="DUMMY_DATA_PATH")

    # Gmail OAuth
    gmail_credentials_path: str = Field(default="credentials.json",
                                        alias="GMAIL_CREDENTIALS_PATH")
    gmail_token_path:       str = Field(default="token.json",
                                        alias="GMAIL_TOKEN_PATH")
    gmail_max_results:      int = Field(default=20,    alias="GMAIL_MAX_RESULTS")

    # 파이프라인
    parallel_agents:     bool = Field(default=True,  alias="PARALLEL_AGENTS")
    max_concurrent_emails: int = Field(default=5,    alias="MAX_CONCURRENT_EMAILS")
    enable_auto_reply:   bool = Field(default=False, alias="ENABLE_AUTO_REPLY")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
