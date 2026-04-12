from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./investment.db"

    futu_host: str = "127.0.0.1"
    futu_port: int = 11111
    futu_trade_pwd: str = ""

    ib_host: str = "127.0.0.1"
    ib_port: int = 7497
    ib_client_id: int = 1

    anthropic_api_key: str = ""
    sync_interval: int = 300
    use_mock_data: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
