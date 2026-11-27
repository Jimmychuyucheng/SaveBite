"""PostgreSQL 連線池（asyncpg）。

設計重點（ARCHITECTURE.md §6.7）：程式啟動時連不上 RDS 也不能結束。
連線池設 min_size=0，建立時不會連線，等第一個請求用到才連；
連不上只讓該請求回 503，不影響 /health 與程式本身。
"""

import logging
from collections.abc import AsyncIterator
from typing import Annotated

import asyncpg
from fastapi import Depends, HTTPException, Request, status

from app.config import Settings

logger = logging.getLogger(__name__)

# 連不上資料庫時會出現的例外
DB_UNAVAILABLE_ERRORS = (
    OSError,
    TimeoutError,
    asyncpg.CannotConnectNowError,
    asyncpg.TooManyConnectionsError,
    asyncpg.InterfaceError,
)


async def create_pool(settings: Settings) -> asyncpg.Pool:
    """建立連線池。min_size=0，所以這裡不會真的連線，DB 沒開也不會失敗。"""
    return await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=0,
        max_size=settings.db_pool_max_size,
        timeout=settings.db_connect_timeout_seconds,  # 建立單一連線的逾時
        max_inactive_connection_lifetime=300,  # 閒置 5 分鐘就關閉，RDS 容錯移轉後能換到新主機
    )


async def get_conn(request: Request) -> AsyncIterator[asyncpg.Connection]:
    """FastAPI dependency：從連線池借一條連線，請求結束後歸還。

    連不上資料庫時回 503，不讓例外變成 500。
    交易請在呼叫端用 `async with conn.transaction():` 明確包起來。
    """
    pool: asyncpg.Pool = request.app.state.db_pool
    settings: Settings = request.app.state.settings
    try:
        conn = await pool.acquire(timeout=settings.db_connect_timeout_seconds)
    except DB_UNAVAILABLE_ERRORS as exc:
        logger.warning("資料庫連線失敗：%r", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable") from exc
    try:
        yield conn
    finally:
        await pool.release(conn)


# 路由參數寫成 `conn: DbConn` 就會自動借連線
DbConn = Annotated[asyncpg.Connection, Depends(get_conn)]
