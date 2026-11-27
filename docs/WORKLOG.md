# 工作紀錄

依模組記錄做過的事、做了什麼決定、結果如何，方便回顧。每個模組內依時間排序（新的在下面）。

- 設計細節以 [ARCHITECTURE.md](ARCHITECTURE.md) 為準，AWS 實際 ID 見 [CONSOLE_SETUP.md](CONSOLE_SETUP.md)
- 時間為台灣時間（UTC+8），另有標示者除外

## 目錄

1. [架構與文件](#1-架構與文件)
2. [決策紀錄](#2-決策紀錄)
3. [AWS 基礎設施](#3-aws-基礎設施)
4. [驗證與實驗](#4-驗證與實驗)
5. [Git 與工作流程](#5-git-與工作流程)
6. [本機開發](#6-本機開發)
7. [待辦](#7-待辦)

---

## 1. 架構與文件

### 2026-11-27 審閱架構文件
- 讀完 `CLAUDE.md`、`docs/ARCHITECTURE.md`，整理出對架構的理解（防超賣、即時推送、降級模式、逾時釋出）
- 列出問題：
  - 🔴 會直接出錯：排程提早觸發導致預約永不釋出、取消沿用釋出 SQL 會失敗、S3 直傳需要 CORS、沒有 NAT 就不能用 SSM、`hold_until` 可能超過 `pickup_end`
  - 🟡 需決定：使用哪個帳號、缺少 `/auth/confirm`、`users` 寫入時機、哪些 API 需登入、SNS 無法依區域過濾、壓測使用者、DLQ 需要 SQS、Scheduler 與 LabRole
  - 🟢 小問題：`alb-sg` 不需 443、排程累積、Redis 發布逾時、相鄰 geohash 格子、PATCH 規則未定義、連線數等

### 2026-11-27 修改 ARCHITECTURE.md（第一版定稿）
- §3、§3.1：改成 CloudFormation，分成 network／base／runtime 三個 stack；runtime 參數 `NatGatewayCount`、`RdsMultiAz`；大約費用表
- §4：NAT 依參數 1 或 2 個、各張路由表內容、`alb-sg` 只開 80、新增 SQS
- §5：`subscriptions` 新增欄位與限制；`users` 改成第一次帶 JWT 時 upsert
- §6.1–6.3：修正預約、取消、領取、釋出、到期下架的 SQL；排程延後 1 分鐘；提早觸發時丟例外讓它重試
- §6.4–6.12：WebSocket 驗證、Redis 發布逾時、SNS filter policy、S3 presigned URL、修改貼文規則、連線數
- §7：API 表加上「需要登入」欄、`/auth/confirm`、壓測登入 `X-Loadtest-User-Id`
- §8–11：Python 3.11、新增環境變數、實驗前要切換的參數、待確認事項

### 2026-11-27 ARCHITECTURE.md 第二次修改
- §6.10：S3 CORS 開發期先用 `*`，runtime stack 建好後改成只允許 ALB 網址和 localhost
- §6.3：新增每 5 分鐘的安全網掃描（EventBridge rule，不需要執行角色），同時作為 Scheduler 的退路；第 5 節加上索引 `reservations_held_until_idx`
- §11：寫下重試由哪一層負責的驗證方法

### 2026-11-27 CLAUDE.md（只留在本機）
- 改成「用 CloudFormation 管理」
- 新增「執行 AWS 指令的規則」：一律用 `--profile savebite-lab`、先確認身分、建立／更新／刪除前要同意、runtime stack 等程式寫好才建
- 新增「Git 規則」：不直接推送到 main、每個工作開 branch 和 PR、不加 Claude 署名、CLAUDE.md 不提交

### 2026-11-27 新增 CONSOLE_SETUP.md
- 記錄部署指令、實際 ID、本機 `.env` 對應值、刪除順序、異動紀錄

### 2026-11-27 新增 WORKLOG.md
- 也就是本文件

---

## 2. 決策紀錄

| 日期 | 決策 | 理由 |
|---|---|---|
| 11-27 | 資源建在組長的 Learner Lab 帳號 `126811246350` | Learner Lab 是每人一個帳號 |
| 11-27 | Pool ID、client ID 等寫進 CONSOLE_SETUP.md | 組員方便重建；這些不是密碼或金鑰 |
| 11-27 | 未登入可以看地圖，但不能收即時推送 | 未登入時改用輪詢 |
| 11-27 | 改用 CloudFormation，分三個 stack | 免費資源常駐，計費資源一個指令建好或刪掉；Terraform 的 state 要共用，CDK／SAM 需要建 IAM role |
| 11-27 | EC2 維持放在私有子網路 | 保留網路分層；成本用 NAT 參數控制 |
| 11-27 | NAT 預設 1 個、實驗時 2 個；RDS 預設單一 AZ、實驗時 Multi-AZ | NAT 是開著時最貴的一項 |
| 11-27 | 接受另外 6 點自行決定的設計：到期下架也延後 1 分鐘、領取要在 `hold_until` 前且只有店家能核銷、訂閱每人一筆且半徑 ≤ 5 公里、S3 CORS 用 `*`、修改貼文規則、§11 待驗證項目 | 見 ARCHITECTURE.md |
| 11-27 | 加上每 5 分鐘的安全網掃描 | 補救排程失敗，同時作為 Scheduler 的退路 |
| 11-27 | GitHub repo 是公開的，仍照常推送含 ID 的文件 | 課程專案可接受；ID 不是金鑰 |
| 11-27 | 之後一律用 branch 和 PR | 由組長確認後才合併 |
| 11-27 | WORKLOG.md 放進 repo（和驗證結果同一個 PR） | 組長可以回顧，組員也看得到進度 |
| 11-27 | 不走 Scheduler 的退路，個別排程照原設計 | 實測 Scheduler + LabRole 可用 |
| 11-27 | 回覆、文件、註解、commit、PR、留言一律用繁體中文；識別字和資源名稱用英文 | 組長要求 |
| 11-27 | CloudFormation 的 `Description`、SG 的 `GroupDescription` 維持英文 | 實測中文會被換成「?」；SG 描述只能用 ASCII，而且修改會讓 SG 重建 |
| 11-27 | 組長負責 C（網路與基礎設施）；A1 骨架屬於 B 的範圍、A2 migration 屬於 A 的範圍，A2 先暫停，交給 A | 避免做到別人的範圍；ARCHITECTURE.md 中 A、B 負責的部分請他們確認 |
| 11-27 | runtime stack 可以分段建立測試，但當天刪除（CLAUDE.md 規則已改） | 不必等程式全部寫好，就能先驗證 NAT、ALB、Auto Scaling |
| 11-27 | 程式碼用「打包上傳 S3」部署到 EC2，不用開機 `git clone` | 版本固定、對得到 commit，兩台不會跑不同版本 |
| 11-27 | RDS 密碼用 Secrets Manager（`ManageMasterUserPassword`）；EC2 t3.small、RDS db.t3.micro；ElastiCache 開發時單一節點 | 第二段實作時採用；已實測可用 |
| 11-27 | 加上 Secrets Manager interface endpoint（runtime stack） | Lambda 在資料子網路沒有對外路由；不把密碼放進環境變數 |
| 11-27 | 測試通過後由 Claude 自己 squash and merge 並繼續；AWS 建立／刪除仍要先同意 | 組長授權；放寬 AWS 審核的部分被權限系統擋下 |

---

## 3. AWS 基礎設施

### 2026-11-27 檢查 AWS CLI 身分
- 發現 default profile 是**另一個帳號**（不是 Learner Lab），所以改用 profile `savebite-lab`
- 確認 `savebite-lab` 的 Arn 是 `assumed-role/voclabs/...`，帳號 `126811246350`

### 2026-11-27 寫 CloudFormation 模板
- `infra/cloudformation/network.yaml`：VPC、6 個子網路、IGW、5 張路由表、S3 Gateway Endpoint、5 個 SG
- `infra/cloudformation/base.yaml`：Cognito user pool 和 public client、S3 照片 bucket、SNS、SQS DLQ、schedule group
- 都通過 `validate-template` 和 `cfn-lint`

### 2026-11-27 部署 savebite-network、savebite-base
- 兩個都 `CREATE_COMPLETE`，費用 $0
- Cognito 預設建成 Essentials 方案（每月 1 萬名活躍使用者內免費）
- 抽查：S3 endpoint 是 available；`lambda-sg` 只能對外連 DB、Redis

### 2026-11-27 模板註解改成中文（PR #2）
- `#` 註解改成繁體中文
- 發現 CloudFormation 會把模板 `Description` 裡的中文換成 `?`（AWS CLI、boto3 都一樣，跟 locale 無關），所以 `Description` 維持英文
- 用 cfn-lint 的解析器比對新舊模板，內容完全相同，不需要更新 stack

### 2026-11-27 刪除測試 user pool `User pool - rrletp`
- 它開了刪除保護、掛著 domain，所以先刪 domain、關掉保護，再刪除 pool

### 2026-11-27 runtime 第一段（`infra/runtime-compute`）
- **寫了**：
  - `runtime.yaml` 第一段：NAT（依 `NatGatewayCount` 建 1 或 2 個）、ALB、target group、Launch Template、Auto Scaling group
  - `base.yaml` 新增 S3 部署檔 bucket
  - `scripts/package-backend.sh`：打包已 commit 的 `backend/` 並上傳
- **EC2 開機流程**：安裝 Python 3.11 → 從 S3 下載後端 → systemd 啟動 uvicorn → 本機 `/health` 正常後用 `cfn-signal` 回報；任何一步失敗就回報失敗
- **部署**：
  - 更新 `savebite-base`：只新增 artifacts bucket
  - 上傳 `releases/backend-a886d49fc215.tar.gz`
  - 建立 runtime：4 分 15 秒
  - 測試完當天刪除：前後共開約 11 分鐘，費用約 $0.03
- 第一段還沒有 RDS，`DATABASE_URL` 指向連不到的位址；程式照樣啟動，`/health` 回 200，剛好也驗證了 §6.7 的設計

### 2026-11-27 runtime 第二段（`infra/runtime-data`）
- **runtime.yaml 新增**：
  - RDS PostgreSQL 16.13：密碼由 RDS 產生並存進 Secrets Manager；刪除 stack 時不留快照
  - ElastiCache Redis 7.1：單一節點
  - Secrets Manager interface endpoint 與 `endpoint-sg`
  - Lambda `savebite-release`：佔位程式；非同步重試 2 次、失敗送 DLQ
  - EventBridge rule `savebite-sweep`：每 5 分鐘觸發一次
- **EC2 user data**：從 Secrets Manager 取得密碼組成 `DATABASE_URL`，並寫入 13 個環境變數。取得密碼的那幾行關閉 `set -x`，避免密碼進日誌；移除第一段的 `AppDatabaseUrl` 參數
- **設計調整**：Lambda 在資料子網路沒有對外路由，連不到 Secrets Manager，所以加上 interface endpoint（約 $0.02／小時）。沒有把密碼放進 Lambda 環境變數，因為 Console 上看得到明文，而且輪替後會失效
- `cfn-lint` 指出 `EngineVersion: "16"` 不能用來建立新的 RDS，改成固定 `16.13`
- **規則**：
  - 使用者授權「測試通過後自己 squash and merge 並繼續」，已寫進 CLAUDE.md
  - 「AWS 建立／刪除不用先問」這一項被權限系統擋下，維持「建立前先列出資源與費用、等同意」

---

## 4. 驗證與實驗

### 2026-11-27 Scheduler + LabRole 驗證 ✅
- **LabRole 的 trust policy 有 `scheduler.amazonaws.com` 和 `events.amazonaws.com`**
- 用 voclabs 身分建立以 LabRole 為執行角色的排程：成功（EC2 那邊能否 PassRole，要等 runtime stack 再測）
- 暫時資源：
  - Lambda `savebite-scheduler-test`（LabRole，非同步重試 2 次，失敗目的地是 `savebite-dlq`）
  - 排程 `test-fail-once`、`test-fail-always`（group `savebite`，retry 2 次，DLQ 是 `savebite-dlq`，執行完自動刪除）
  - 觸發時間 10:48 UTC，run_id `1795776333`
- 結果：

  | 測試 | 執行時間（UTC） | 結果 |
  |---|---|---|
  | `fail-once` | 10:48:26 → 10:49:24 | 失敗 → 重試成功（同一個 request ID） |
  | `fail-always` | 10:48:12 → 10:49:19 → 10:51:34 | 3 次都失敗 → DLQ 收到 1 則 `RetriesExhausted` |

- 結論：
  - **函式錯誤由 Lambda 的非同步重試負責**（約 1 分鐘、2 分鐘），Scheduler 不會重試函式錯誤
  - 失敗訊息由 Lambda 的失敗目的地送進 DLQ
  - 觸發時間比排定的晚 12 到 26 秒
  - 排程執行完會自動刪除
- 不需要走退路，安全網掃描保留用來補救
- 已刪除全部暫時資源並清空 DLQ
- 結果寫回 ARCHITECTURE.md §6.3、§11，以及 CONSOLE_SETUP.md §6、§7

### 2026-11-27 runtime 第一段測試 ✅
- ALB `/health` 回 200；兩台 EC2 分別在 1a、1b，都 healthy
- SSM：兩台 Online，Run Command 可以執行（**SSM 經 NAT 可用**）
- 兩台的對外 IP 都是 NAT 的 EIP，1b 跨 AZ 走 1a 的 NAT；連 Cognito endpoint 正常
- **終止 1a 的 EC2（實驗一預演）**，同時每 0.5 秒打一次 ALB：
  - 約 19 秒內 6 個請求失敗（3 個 502、3 個逾時），其他請求仍然成功，**服務沒有完全中斷**
  - 整段 147 個請求中失敗率 4.1%
  - Auto Scaling 約 56 秒後發現；**2 分 17 秒後恢復成 2 台**
  - 失敗集中在 ALB 還沒判定不健康的期間（10 秒一次、連續 2 次失敗才判定）
- 小插曲：探測腳本跑到 13:31:29 就停了（應該跑 8 分鐘），推測是背景 shell 結束時被一起關掉；這時已經涵蓋到恢復完成，不影響結論。正式實驗要改用不會被中斷的方式（例如 k6 或 `nohup`）
- 結果寫進 CONSOLE_SETUP.md §8、ARCHITECTURE.md §11

### 2026-11-27 runtime 第二段測試 ✅
- 建立花 13 分 26 秒。**ElastiCache、RDS 管理的密碼、Secrets Manager interface endpoint 在 Learner Lab 都能用**
- ALB `/health` 回 200
- 兩台 EC2：經 endpoint 讀到密碼；asyncpg 連上 RDS（16.13，`savebite_admin@savebite`）；Redis 回 `PONG`；環境變數檔權限 640；開機日誌沒有密碼
- **EC2 可以 PassRole LabRole**：在 EC2 上建立排程成功，14:49:00 排定、14:49:11 觸發 Lambda，執行完自動刪除
- Lambda（VPC 內）：連 DB 21 ms、連 Redis 10 ms，Secrets Manager 讀得到密碼
- 安全網掃描 rule：14:43、14:48、14:53、14:58 各觸發一次
- DLQ 0 則
- 測試途中 zsh 不會拆開變數裡的參數，SSM 指令第一次沒送出去；改成 bash 腳本後重跑成功
- **刪除花了 24 分鐘**（RDS 和 Lambda 的網路介面）。剛刪完時還有 ElastiCache 的網路介面和 RDS 自動備份快照，約 4 分鐘後由 AWS 自動清除
- 從建立到刪除完成約 55 分鐘，費用約 $0.18
- 結果寫進 CONSOLE_SETUP.md §8、ARCHITECTURE.md §4、§11

---

## 5. Git 與工作流程

| 日期 | 動作 | commit／branch |
|---|---|---|
| 11-27 | CLAUDE.md 用 `.git/info/exclude` 排除 | |
| 11-27 | commit 架構文件 | `be6c758` |
| 11-27 | commit 模板和 CONSOLE_SETUP.md | `a86d665` |
| 11-27 | 推送到 main（branch 規則訂下之前） | `d5a7833..a86d665` |
| 11-27 | 開始用 branch 開發 | `docs/scheduler-verification` |
| 11-27 | commit 驗證結果和 WORKLOG.md，開 PR | `docs/scheduler-verification` → [PR #1](https://github.com/Jimmychuyucheng/SaveBite/pull/1) |
| 11-27 | 規定所有文字一律用繁體中文；PR #1 的標題、描述、commit 訊息改成中文（commit 改寫後用 `--force-with-lease` 推送） | `9824e28` |
| 11-27 | main 上已有的兩個英文 commit（`be6c758`、`a86d665`）不改寫，避免對 main 強制推送 | |
| 11-27 | 模板註解改成中文 | `chore/zh-comments` → [PR #2](https://github.com/Jimmychuyucheng/SaveBite/pull/2) |
| 11-27 | 合併 PR #1、#2（用 merge commit；之後建議改用 squash） | `e9586fe`、`b74fbe6` |
| 11-27 | A1 本機開發骨架 | `feat/backend-skeleton` → PR #3（squash 合併 `a886d49`） |
| 11-27 | runtime 第一段 | `infra/runtime-compute` → PR #4（squash 合併 `38b7aa8`） |
| 11-27 | runtime 第二段 | `infra/runtime-data` |

---

## 6. 本機開發

### 2026-11-27 A1 本機開發骨架（`feat/backend-skeleton`）
- **環境**：本機沒有 Python 3.11，用 `uv python install 3.11` 安裝，建立 `backend/.venv`（維持 3.11，和 EC2 的 Amazon Linux 2023 一致）
- **新增檔案**：
  - 根目錄：`docker-compose.yml`（postgres:16、redis:7，只綁 127.0.0.1，帳密從 `.env` 讀）、`.env.example`（已填入 CONSOLE_SETUP.md 的 AWS ID，密碼留空）、`.gitignore`、README 本機啟動步驟
  - `backend/`：`requirements.txt`、`requirements-dev.txt`（版本固定）、`pyproject.toml`（ruff、pytest 設定）
  - `backend/app/`：`config.py`（pydantic-settings）、`db.py`（asyncpg 連線池、`DbConn` dependency）、`routers/health.py`、`main.py`（`create_app()`、lifespan）
  - `backend/tests/`：`test_health.py`、`test_db.py`、`conftest.py`
  - `frontend/`、`lambda/release/`、`load-tests/`、`scripts/`：先放 README 佔位
- **設計重點**：
  - 連線池 `min_size=0`，所以 **DB 沒開也能啟動**，連不上只讓該請求回 503（§6.7）
  - 連線閒置 5 分鐘就關閉，RDS 容錯移轉後會換到新主機
  - `/health` 不碰 DB
- **途中處理的問題**：
  - ruff `B008`：`Depends` 改用 `Annotated` 寫法，定義共用型別 `DbConn`
  - Starlette 1.10 把 TestClient 依賴的 `httpx` 改成 `httpx2`，舊套件會出現棄用警告，改裝 `httpx2`
  - 環境變數的優先順序高於 `.env`，所以 `conftest.py` 只在 `.env` 不存在時才給預設的 `DATABASE_URL`，避免蓋掉真實設定
- **驗證**：
  - `ruff check`、`ruff format --check` 通過
  - `pytest` 3 個全過，包含連到真實 PostgreSQL 16 的測試
  - 實際啟動 uvicorn：DB 正常、執行中停掉 DB、DB 停著才啟動，三種情況 `/health` 都回 200
- 本機 `.env` 用隨機產生的本機密碼，已確認被 `.gitignore` 排除

### 下一步
- **A2**（Alembic migration）屬於 A 組員的範圍，暫停，交給 A

---

## 7. 待辦

- [x] 完成 Scheduler 驗證，把結果寫回 ARCHITECTURE.md §6.3、§11 和 CONSOLE_SETUP.md
- [x] 刪除 Scheduler 驗證的暫時資源
- [x] 推送 `docs/scheduler-verification` 並開 PR（含 WORKLOG.md）
- [x] 組長確認並合併 PR #1（驗證結果與工作紀錄）、PR #2（模板中文註解）
- [x] A1 本機開發骨架（PR #3 已合併）
- [ ] 通知 A、B：ARCHITECTURE.md 中他們負責的部分（§6.1–6.4、§6.9）請確認；A1 骨架交給 B 接手
- [ ] A2 資料表 migration（**A 組員**負責）
- [x] runtime 第一段：NAT、ALB、Auto Scaling（已測試並刪除）
- [x] runtime 第二段：RDS（Secrets Manager 密碼）、ElastiCache、Lambda、安全網掃描 EventBridge rule（已測試並刪除）
- [x] 待驗證：ElastiCache 在 Lab 能否建立、EC2 能否 PassRole LabRole、EC2 能否讀 Secrets Manager（全部可以）
- [ ] 監控（第三段）：CloudWatch agent（應用日誌）、告警（ALB 5xx、UnHealthyHostCount、RDS、DLQ）、dashboard
- [ ] 部署與刪除 runtime 的腳本
- [ ] Lambda 正式程式（**A 組員**）：替換 `savebite-release` 的佔位程式，沿用現有的重試、DLQ、觸發設定
- [ ] 應用程式改用非主帳號連 DB（目前用 RDS 主帳號 `savebite_admin`），和 A 討論 migration 時一起處理
- [ ] runtime 建好後：S3 CORS 改成只允許 ALB 網址和 localhost
- [ ] 實驗一（`NatGatewayCount=2`，配合 A 的 k6 腳本）
