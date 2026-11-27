"""應用程式設定：一律從環境變數讀取（本機可放在 repo 根目錄的 .env）。

欄位名稱對應 ARCHITECTURE.md §8.3 的環境變數（不分大小寫）。
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# repo 根目錄的 .env；EC2 上不放 .env，改由 systemd 設定環境變數（檔案不存在時會被忽略）
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # local：本機開發；dev：雲端開發；loadtest：壓測（啟用 X-Loadtest-User-Id，見 §7.1）；prod：正式
    app_env: Literal["local", "dev", "loadtest", "prod"] = "local"
    log_level: str = "INFO"

    # PostgreSQL，格式 postgresql://user:password@host:5432/dbname
    database_url: str
    db_pool_max_size: int = Field(default=10, ge=1)
    db_connect_timeout_seconds: float = Field(default=5.0, gt=0)

    redis_url: str = "redis://localhost:6379/0"

    aws_region: str = "us-east-1"

    # 以下在對應功能實作時才會用到，目前允許留空
    cognito_user_pool_id: str | None = None
    cognito_app_client_id: str | None = None
    photo_bucket: str | None = None
    sns_topic_arn: str | None = None
    release_lambda_arn: str | None = None
    scheduler_role_arn: str | None = None
    scheduler_group: str = "savebite"
    scheduler_dlq_arn: str | None = None

    reservation_hold_minutes: int = Field(default=30, ge=1)


@lru_cache
def get_settings() -> Settings:
    """取得設定（整個程式共用同一份）。缺少必要值時在這裡就會報錯。"""
    return Settings()
