"""FastAPI 進入點。

本機啟動（在 backend/ 目錄）：uvicorn app.main:app --reload --port 8000
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.db import create_pool
from app.routers import health


def create_app(settings: Settings | None = None) -> FastAPI:
    """建立 app。測試時可以傳入自訂的 settings。"""
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # 建立連線池不會真的連線（min_size=0），所以 DB 沒開也能正常啟動
        app.state.db_pool = await create_pool(settings)
        try:
            yield
        finally:
            await app.state.db_pool.close()

    app = FastAPI(title="SaveBite API", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health.router)
    return app


app = create_app()
