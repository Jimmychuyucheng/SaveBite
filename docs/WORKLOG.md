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

### 2026-11-27 刪除測試 user pool `User pool - rrletp`
- 它開了刪除保護、掛著 domain，所以先刪 domain、關掉保護，再刪除 pool

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

---

## 5. Git 與工作流程

| 日期 | 動作 | commit／branch |
|---|---|---|
| 11-27 | CLAUDE.md 用 `.git/info/exclude` 排除 | |
| 11-27 | commit 架構文件 | `be6c758` |
| 11-27 | commit 模板和 CONSOLE_SETUP.md | `a86d665` |
| 11-27 | 推送到 main（branch 規則訂下之前） | `d5a7833..a86d665` |
| 11-27 | 開始用 branch 開發 | `docs/scheduler-verification` |
| 11-27 | commit 驗證結果和 WORKLOG.md（PR 待開） | `docs/scheduler-verification` |

---

## 6. 本機開發

尚未開始。計畫（A 線）：

- **A1**：repo 目錄、`docker-compose.yml`（postgres:16、redis:7）、FastAPI 骨架（`pydantic-settings`、`/health`、asyncpg 連線池）、`.gitignore`、`.env.example`、README
- **A2**：Alembic migration（照 ARCHITECTURE.md 第 5 節的 SQL）

---

## 7. 待辦

- [x] 完成 Scheduler 驗證，把結果寫回 ARCHITECTURE.md §6.3、§11 和 CONSOLE_SETUP.md
- [x] 刪除 Scheduler 驗證的暫時資源
- [ ] 推送 `docs/scheduler-verification` 並開 PR（含 WORKLOG.md），等組長確認後合併
- [ ] A1 本機開發骨架
- [ ] A2 資料表 migration
- [ ] runtime stack 建好後：S3 CORS 改成只允許 ALB 網址和 localhost；測試 EC2 能否 PassRole LabRole
