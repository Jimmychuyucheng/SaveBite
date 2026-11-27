"""健康檢查。

只確認程式本身活著，**不檢查 RDS 或 Redis**（ARCHITECTURE.md §6.7）。
如果依賴外部服務，RDS 或 Redis 一故障，兩台 EC2 會同時被 ALB 判定不健康並被替換，
反而造成全面中斷。
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
