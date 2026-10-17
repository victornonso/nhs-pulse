from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    database_url: str
    migration_database_url: str
    worker_database_url: str = ""
    session_secret: str
    admin_key: str = ""
    app_origin: str = "http://127.0.0.1:3020"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-flash"
    raw_storage: Path = ROOT / ".local/raw"


settings = Settings()
