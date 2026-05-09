from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "AtlasPure API"
    api_base_url: str = "https://api.atlaspure.shop"
    frontend_url: str = "https://atlaspure.shop"

    database_url: str = "postgresql+psycopg://atlaspure:atlaspure@localhost:5432/atlaspure"

    cors_origins: str = "https://atlaspure.shop,https://www.atlaspure.shop,http://localhost:3000"

    google_sheets_webhook_url: str = ""
    google_sheets_webhook_secret: str = ""

    meta_pixel_id: str = ""
    meta_access_token: str = ""
    meta_test_event_code: str = ""

    tiktok_pixel_id: str = ""
    tiktok_access_token: str = ""
    tiktok_test_event_code: str = ""

    snap_pixel_id: str = ""
    snapchat_access_token: str = ""
    snap_test_event_code: str = ""

    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def db_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
