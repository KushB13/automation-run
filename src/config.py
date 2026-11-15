from __future__ import annotations

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")

    x_api_key: str = Field(default="", alias="X_API_KEY")
    x_api_secret: str = Field(default="", alias="X_API_SECRET")
    x_access_token: str = Field(default="", alias="X_ACCESS_TOKEN")
    x_access_token_secret: str = Field(default="", alias="X_ACCESS_TOKEN_SECRET")
    x_handle: str = Field(default="", alias="X_HANDLE")

    github_token: str = Field(default="", alias="GITHUB_TOKEN")

    dry_run: bool = Field(default=False, alias="DRY_RUN")
    source_override: str = Field(default="auto", alias="SOURCE_OVERRIDE")
    post_format_override: str = Field(default="auto", alias="POST_FORMAT_OVERRIDE")

    history_path: Path = Field(default=Path("data/history.json"), alias="HISTORY_PATH")
    output_dir: Path = Field(default=Path("output"), alias="OUTPUT_DIR")
    max_tweet_chars: int = Field(default=280, alias="MAX_TWEET_CHARS")
    dedup_cooldown_days: int = Field(default=30, alias="DEDUP_COOLDOWN_DAYS")

    @property
    def has_x_credentials(self) -> bool:
        return all(
            [
                self.x_api_key.strip(),
                self.x_api_secret.strip(),
                self.x_access_token.strip(),
                self.x_access_token_secret.strip(),
            ]
        )
