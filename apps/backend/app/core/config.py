from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[2] / "flowcraft.db"


class Settings(BaseSettings):
    app_name: str = "Flowcraft API"
    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_url: str = f"sqlite:///{DEFAULT_DATABASE_PATH}"
    bitrix_key_path: Path = DEFAULT_DATABASE_PATH.parent / ".secrets" / "bitrix.key"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
