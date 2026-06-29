"""
Pydantic BaseSettings and derivatives for this repo.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    DWD_BASE_URL: str = "https://opendata.dwd.de/weather/radar"
    CACHE_DIR: str = "cache"
    DATA_CACHE_TTL: int = 3600  # 1 hour
    DATA_DIR: str = "../data"

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def data_dir_path(self) -> Path:
        path = Path(self.DATA_DIR).expanduser()
        if path.is_absolute():
            return path
        return (BACKEND_ROOT / path).resolve()


settings = Settings()
