from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration comes from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = ""
    admin_ids: Annotated[list[int], NoDecode] = []
    database_url: str = "sqlite+aiosqlite:///./dogs_bet.db"

    # Channels users must join before using the bot (leave empty for now).
    # The bot must be an admin in each channel so it can check membership.
    required_channels: Annotated[list[str], NoDecode] = []

    support_username: str = ""  # without @
    store_name: str = "Dogs Bet"
    platform_website: str = ""  # e.g. https://dogsbet.com

    # SYP exchange rate (SYP per 1 USD). Admin can change it from the bot.
    default_syp_rate: float = 13000.0
    syp_rate_api_url: str = ""
    syp_rate_json_key: str = "rate"
    syp_rate_refresh_minutes: int = 30

    # Agent API (optional — for real platform integration later)
    agent_api_base_url: str = ""
    agent_username: str = ""
    agent_password: str = ""

    # Points / display currency name shown to users (like NPS in Wolf)
    points_name: str = "USD"
    points_rate: float = 1.0  # how many points = 1 USD (for display)

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_ids(cls, value):
        if isinstance(value, str):
            return [int(part) for part in value.replace(" ", "").split(",") if part]
        if isinstance(value, int):
            return [value]
        return value

    @field_validator("required_channels", mode="before")
    @classmethod
    def _split_channels(cls, value):
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value


settings = Settings()
