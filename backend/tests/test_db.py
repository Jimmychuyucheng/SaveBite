"""實際連線本機 PostgreSQL（需要先 docker compose up -d）。連不上時略過。"""

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import DbConn
from app.main import create_app

pytestmark = pytest.mark.db


@pytest.fixture
def settings() -> Settings:
    return Settings()  # 讀 .env 或環境變數


@pytest.fixture
async def _require_db(settings: Settings) -> None:
    try:
        conn = await asyncpg.connect(settings.database_url, timeout=2)
    except (OSError, TimeoutError, asyncpg.PostgresError) as exc:
        pytest.skip(f"本機 PostgreSQL 未啟動或 DATABASE_URL 設定錯誤：{exc!r}")
    await conn.close()


@pytest.mark.usefixtures("_require_db")
def test_get_conn_queries_database(settings: Settings):
    app = create_app(settings)

    @app.get("/_test/db")
    async def _uses_db(conn: DbConn):
        return {"version": await conn.fetchval("SHOW server_version")}

    with TestClient(app) as client:
        resp = client.get("/_test/db")
    assert resp.status_code == 200
    # 本機與 RDS 都用 PostgreSQL 16
    assert resp.json()["version"].startswith("16")
