from dataclasses import dataclass
from functools import lru_cache
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_url: str
    openrouter_key: str
    supabase_url: str
    supabase_anon_key: str
    planner_model: str = "openai/gpt-5.6-terra"
    fast_model: str = "google/gemini-3.5-flash-lite"
    content_model: str = "anthropic/claude-sonnet-5"
    embedding_model: str = "openai/text-embedding-3-small"
    transcription_model: str = "openai/whisper-large-v3-turbo"
    speech_model: str = "hexgrad/kokoro-82m"
    speech_voice: str = "af_heart"
    environment: str = "production"
    local_auth_secret: str = ""
    supabase_service_role_key: str = ""
    max_run_cost: float = 1.0
    max_workspace_runs: int = 60
    max_tool_rounds: int = 12
    worker_lease_seconds: int = 120


@lru_cache
def settings() -> Settings:
    if os.getenv("ENV_FILE"):
        load_dotenv(os.environ["ENV_FILE"], override=False)
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        openrouter_key=os.environ["OPENROUTER_API_KEY"],
        supabase_url=os.getenv("SUPABASE_URL", "").rstrip("/"),
        supabase_anon_key=os.getenv("SUPABASE_ANON_KEY", ""),
        planner_model=os.getenv("PLANNER_MODEL", "openai/gpt-5.6-terra"),
        fast_model=os.getenv("FAST_MODEL", "google/gemini-3.5-flash-lite"),
        content_model=os.getenv("CONTENT_MODEL", "anthropic/claude-sonnet-5"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small"),
        transcription_model=os.getenv("TRANSCRIPTION_MODEL", "openai/whisper-large-v3-turbo"),
        speech_model=os.getenv("SPEECH_MODEL", "hexgrad/kokoro-82m"),
        speech_voice=os.getenv("SPEECH_VOICE", "af_heart"),
        environment=os.getenv("ENVIRONMENT", "production"),
        local_auth_secret=os.getenv("LOCAL_AUTH_SECRET", ""),
        supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
        max_run_cost=float(os.getenv("MAX_RUN_COST", "1.0")),
        max_workspace_runs=int(os.getenv("MAX_WORKSPACE_RUNS", "60")),
    )
