"""/health 與「DB 掛掉時程式仍要活著」的行為（ARCHITECTURE.md §6.7）。"""

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import DbConn
from app.main import create_app

# 指向沒有服務的 port，模擬 RDS 故障
UNREACHABLE_DB = "postgresql://nobody:x@127.0.0.1:1/none"


def _settings_with_unreachable_db() -> Settings:
    return Settings(database_url=UNREACHABLE_DB, db_connect_timeout_seconds=1)


def test_health_ok_even_when_db_unreachable():
    app = create_app(_settings_with_unreachable_db())
    with TestClient(app) as client:  # with 會執行 lifespan（建立連線池）
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_db_dependency_returns_503_when_db_unreachable():
    app = create_app(_settings_with_unreachable_db())

    # 測試專用路由：用 get_conn 借連線
    @app.get("/_test/db")
    async def _uses_db(conn: DbConn):
        return {"one": await conn.fetchval("SELECT 1")}

    with TestClient(app) as client:
        resp = client.get("/_test/db")
        # DB 失敗只影響這個請求，/health 照樣正常
        assert client.get("/health").status_code == 200
    assert resp.status_code == 503
