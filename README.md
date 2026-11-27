# SaveBite
SaveBite 惜食地圖是剩食即時媒合平台。餐廳、麵包店、活動主辦方發布剩下仍可食用的食物（種類、數量、地點、領取時間、價格或免費），附近的人在地圖上查詢並預約領取。

- 架構與設計：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- AWS 部署紀錄與實際 ID：[docs/CONSOLE_SETUP.md](docs/CONSOLE_SETUP.md)
- 工作紀錄：[docs/WORKLOG.md](docs/WORKLOG.md)

## 目錄結構

```
backend/                 FastAPI（REST、WebSocket、前端靜態檔）
frontend/                React（尚未建立）
lambda/release/          逾時釋出、到期下架、安全網掃描（尚未建立）
infra/cloudformation/    CloudFormation 模板（network、base、runtime）
load-tests/              k6 壓測腳本（尚未建立）
scripts/                 部署、資料匯入、模擬資料（尚未建立）
docs/                    文件
docker-compose.yml       本機 PostgreSQL 16 與 Redis 7
```

## 本機開發

### 需要的工具

- Docker Desktop（跑 PostgreSQL 與 Redis）
- Python 3.11（和 EC2 的 Amazon Linux 2023 一致）。沒有的話可以用 [uv](https://docs.astral.sh/uv/) 安裝：`uv python install 3.11`

### 1. 設定環境變數

```bash
cp .env.example .env
```

打開 `.env`，替 `POSTGRES_PASSWORD` 取一個本機用的密碼，並把同一個密碼填進 `DATABASE_URL`。AWS 相關的值已經填好（來自 CONSOLE_SETUP.md）。

### 2. 啟動 PostgreSQL 與 Redis

```bash
docker compose up -d
docker compose ps        # 兩個服務的 STATUS 都要顯示 healthy
```

停止用 `docker compose down`；連資料一起清空用 `docker compose down -v`。

### 3. 建立 Python 虛擬環境並安裝套件

```bash
cd backend
python3.11 -m venv .venv          # 或：uv venv --python 3.11 .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### 4. 啟動後端

```bash
# 在 backend/ 目錄、已啟用 .venv
uvicorn app.main:app --reload --port 8000
```

確認：

```bash
curl http://localhost:8000/health      # → {"status":"ok"}
```

API 文件：http://localhost:8000/docs

### 5. 測試與 lint

```bash
# 在 backend/ 目錄、已啟用 .venv
pytest           # 標記 db 的測試需要 docker compose 已啟動，否則會自動略過
ruff check .
ruff format --check .
```

## 開發流程

- 不直接推送到 `main`。每個工作開一個 branch（例如 `feat/...`、`docs/...`、`infra/...`、`fix/...`），完成後開 Pull Request，確認後才合併
- `.env` 不提交；密碼與金鑰不寫進程式碼
- 文件、註解、commit 訊息、PR 一律用繁體中文
