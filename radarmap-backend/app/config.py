"""
Pydantic BaseSettings and derivatives for this repo.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DWD_RADVOR_BASE_URL: str = "https://opendata.dwd.de/weather/radar/radvor"
    CACHE_DIR: str = "cache"
    DATA_CACHE_TTL: int = 3600  # 1 hour

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
