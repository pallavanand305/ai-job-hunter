from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "AI Job Hunter"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8000

    database_url: str = Field(default=f"sqlite:///{(DATA_DIR / 'jobhunter.db').as_posix()}")

    data_dir: Path = DATA_DIR
    uploads_dir: Path = DATA_DIR / "uploads"
    artifacts_dir: Path = DATA_DIR / "artifacts"

    # LLM: primary -> secondary -> template fallback.
    # Model names must come from env only; no model ids are hardcoded in provider code.
    llm_primary_provider: str = "gemini"
    llm_primary_model: str = ""
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    llm_secondary_provider: str = "groq"
    llm_secondary_model: str = ""
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    openrouter_api_key: str = ""
    openrouter_model: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_allow_ollama: bool = False
    llm_timeout: int = 120
    llm_max_tokens: int = 4096
    llm_max_retries: int = 1
    llm_backoff_seconds: float = 2.0
    llm_max_retry_wait_seconds: float = 5.0
    llm_min_interval_seconds: float = 3.0
    llm_daily_call_limit: int = 200
    llm_cache_enabled: bool = True
    tailor_target_score: int = 90

    # Legacy LLM settings kept for backward compatibility.
    llm_provider: str = "auto"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # Scheduler
    scheduler_enabled: bool = True
    discovery_hour: int = 9
    discovery_minute: int = 0
    match_interval_minutes: int = 120
    gmail_sync_minutes: int = 60
    timezone: str = "Asia/Kolkata"

    # Job platform connectors (optional keys / permitted alert feeds)
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "in"
    jooble_api_key: str = ""
    linkedin_feed_url: str = ""
    naukri_feed_url: str = ""
    indeed_feed_url: str = ""
    instahyre_feed_url: str = ""
    wellfound_feed_url: str = ""

    # Gmail OAuth (optional)
    google_client_secrets: str = str(DATA_DIR / "google_credentials.json")
    google_token_file: str = str(DATA_DIR / "google_token.json")
    gmail_enable_send: bool = False
    gmail_query: str = "newer_than:30d (interview OR application OR recruiter OR assessment OR offer)"

    # Defaults used when seeding a fresh profile
    default_user_name: str = "Pallav Anand"
    default_user_email: str = "pallavanand757@gmail.com"
    default_user_location: str = "Noida, India"
    default_roles: str = (
        "AI Engineer,Python Backend Engineer,MLOps Engineer,DevOps Engineer,"
        "GenAI Engineer,Cloud Engineer,Software Engineer"
    )
    default_remote_ok: bool = True
    default_min_salary: int = 0
    default_currency: str = "INR"

    # Safety: never auto-send anything without explicit approval
    require_approval: bool = True

    # Stale job expiry: jobs not seen for this many days are marked stale
    stale_days: int = 30

    @property
    def roles(self) -> list[str]:
        return [r.strip() for r in self.default_roles.split(",") if r.strip()]

    @property
    def google_enabled(self) -> bool:
        return Path(self.google_client_secrets).exists()

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.artifacts_dir):
            Path(d).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    os.environ.setdefault("JOBHUNTER_HOME", str(BASE_DIR))
    return settings


settings = get_settings()
