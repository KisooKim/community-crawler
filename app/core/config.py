from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./gae9.db"

    # App
    debug: bool = True
    secret_key: str = "dev-secret-key"
    api_v1_prefix: str = "/api/v1"
    api_base_url: str = "http://localhost:8000"

    # Supabase Storage
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = ""

    # CORS
    allowed_origins: list[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
