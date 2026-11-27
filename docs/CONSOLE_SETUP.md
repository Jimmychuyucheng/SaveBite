# AWS 部署紀錄

所有 AWS 資源用 CloudFormation 管理（設計見 [ARCHITECTURE.md](ARCHITECTURE.md) §3.1）。本文件記錄部署指令與實際建立出來的 ID，讓組員能照著重建。**不記錄密碼或金鑰。**

- 帳號：組長的 Learner Lab（`126811246350`），Region `us-east-1`
- 模板：`infra/cloudformation/`

## 0. 事前準備

1. Learner Lab 頁面按 **Start Lab**，等圓點變綠
2. **AWS Details → AWS CLI: Show**，把三行憑證貼進 `~/.aws/credentials` 的 `[savebite-lab]` profile（不要覆蓋 `[default]`）。憑證約 4 小時過期，過期就重貼
3. 每次執行建立、更新、刪除前先確認身分，Arn 必須是 `assumed-role/voclabs/...`：

   ```bash
   aws sts get-caller-identity --profile savebite-lab
   ```

## 1. 部署狀態

| Stack | 狀態 | 建立日期 | 費用 |
|---|---|---|---|
| `savebite-network` | ✅ `CREATE_COMPLETE` | 2026-11-27 | $0 |
| `savebite-base` | ✅ `UPDATE_COMPLETE`（11-27 新增 artifacts bucket） | 2026-11-27 | $0（Cognito Essentials 每月 1 萬名活躍使用者內免費） |
| `savebite-runtime` | ⬜ 目前不存在。第一、二段已在 11-27 測試後刪除（見 §8） | | 第一加第二段約 $0.19／小時 |

## 2. savebite-network

### 部署指令

```bash
aws cloudformation create-stack --profile savebite-lab --region us-east-1 \
  --stack-name savebite-network \
  --template-body file://infra/cloudformation/network.yaml \
  --tags Key=project,Value=savebite
aws cloudformation wait stack-create-complete --profile savebite-lab --region us-east-1 \
  --stack-name savebite-network
```

修改模板後改用 `update-stack`（參數相同），等待改用 `stack-update-complete`。

參數：`AzA=us-east-1a`、`AzB=us-east-1b`（預設值）。

### 實際 ID

| 項目 | 名稱 | CIDR／說明 | ID |
|---|---|---|---|
| VPC | `savebite-vpc` | `10.0.0.0/16`，DNS hostnames 開啟 | `vpc-0fdf175997472a572` |
| 公有子網路 A | `savebite-public-a` | `10.0.1.0/24`，us-east-1a | `subnet-09a7914ee74c089b8` |
| 公有子網路 B | `savebite-public-b` | `10.0.2.0/24`，us-east-1b | `subnet-0f78d65d959d7817a` |
| 應用子網路 A | `savebite-app-a` | `10.0.11.0/24`，us-east-1a | `subnet-0e0144635316809c8` |
| 應用子網路 B | `savebite-app-b` | `10.0.12.0/24`，us-east-1b | `subnet-013fc59dacfe7cb14` |
| 資料子網路 A | `savebite-data-a` | `10.0.21.0/24`，us-east-1a | `subnet-0d5c56a9aa86e8326` |
| 資料子網路 B | `savebite-data-b` | `10.0.22.0/24`，us-east-1b | `subnet-00fdc650e5ffb7aa6` |
| 應用路由表 A | `savebite-rt-app-a` | NAT 路由由 runtime stack 加上 | `rtb-0427b68022bf66bd7` |
| 應用路由表 B | `savebite-rt-app-b` | NAT 路由由 runtime stack 加上 | `rtb-05a6e98c75480a855` |
| S3 Gateway Endpoint | | 掛在 4 張私有路由表 | `vpce-0fe8455ce98b197c5` |
| SG | `alb-sg` | 入：80 ← `0.0.0.0/0` | `sg-067ae557a91d1824d` |
| SG | `app-sg` | 入：8000 ← `alb-sg` | `sg-05ac467d2dd9e4004` |
| SG | `lambda-sg` | 無入站；出：5432 → `db-sg`、6379 → `redis-sg` | `sg-0310bbcb4e7793731` |
| SG | `db-sg` | 入：5432 ← `app-sg`、`lambda-sg` | `sg-091f06d9e719680a5` |
| SG | `redis-sg` | 入：6379 ← `app-sg`、`lambda-sg` | `sg-0892a6003fbd1f1b0` |

其他沒列 ID 的資源：Internet Gateway `savebite-igw`、公有路由表 `savebite-rt-public`（`0.0.0.0/0 → IGW`）、資料路由表 `savebite-rt-data-a`／`-b`（只有 local 和 S3 endpoint）。

設定重點：
- 所有子網路都**不自動配公有 IP**（公有 IPv4 要收費，ALB 和 NAT 會自己取得）
- `lambda-sg` 有一條 `icmp → 127.0.0.1/32` 的佔位規則，它存在是為了移除預設的「全部允許對外」，不會比對到任何流量，**不要刪**

## 3. savebite-base

### 部署指令

```bash
aws cloudformation create-stack --profile savebite-lab --region us-east-1 \
  --stack-name savebite-base \
  --template-body file://infra/cloudformation/base.yaml \
  --tags Key=project,Value=savebite
aws cloudformation wait stack-create-complete --profile savebite-lab --region us-east-1 \
  --stack-name savebite-base
```

參數：`PhotoCorsOrigins=*`（開發期）、`PhotoRetentionDays=30`。

### 實際 ID

| 項目 | 名稱 | ID／ARN |
|---|---|---|
| Cognito user pool | `savebite-users` | `us-east-1_DkMCcYzHj` |
| Cognito app client | `savebite-web`（public，無 secret） | `10smpea8iso4956j551o8318lg` |
| S3 照片 bucket | `savebite-photos-126811246350` | `arn:aws:s3:::savebite-photos-126811246350` |
| S3 部署檔 bucket | `savebite-artifacts-126811246350` | 放 `releases/backend-<sha>.tar.gz`，60 天後刪除 |
| SNS topic | `savebite-new-listings` | `arn:aws:sns:us-east-1:126811246350:savebite-new-listings` |
| SQS DLQ | `savebite-dlq`（保留 14 天） | `arn:aws:sqs:us-east-1:126811246350:savebite-dlq` |
| Scheduler schedule group | `savebite` | |

設定重點：
- User pool：用 email 登入、必填 `email` 和 `name`、開放自行註冊、email 驗證碼、密碼至少 8 碼且含小寫與數字、用 Cognito 內建寄信（每天約 50 封）
- App client：`ALLOW_USER_PASSWORD_AUTH`、`ALLOW_REFRESH_TOKEN_AUTH`；ID／access token 60 分鐘、refresh token 30 天
- S3：Block Public Access 全開、SSE-S3 加密、CORS 允許 `PUT`／`GET`、`photos/` 下的物件 30 天後刪除、未完成的 multipart upload 1 天後清除

### ⚠️ runtime stack 建好後要做

把 S3 CORS 改成只允許 ALB 網址和 localhost（ARCHITECTURE.md §6.10）：

```bash
aws cloudformation update-stack --profile savebite-lab --region us-east-1 \
  --stack-name savebite-base \
  --template-body file://infra/cloudformation/base.yaml \
  --parameters 'ParameterKey=PhotoCorsOrigins,ParameterValue="http://<ALB DNS>,http://localhost:5173,http://localhost:8000"'
```

## 4. 本機 `.env` 對應值

```bash
AWS_REGION=us-east-1
AWS_PROFILE=savebite-lab
COGNITO_USER_POOL_ID=us-east-1_DkMCcYzHj
COGNITO_APP_CLIENT_ID=10smpea8iso4956j551o8318lg
PHOTO_BUCKET=savebite-photos-126811246350
SNS_TOPIC_ARN=arn:aws:sns:us-east-1:126811246350:savebite-new-listings
SCHEDULER_GROUP=savebite
SCHEDULER_DLQ_ARN=arn:aws:sqs:us-east-1:126811246350:savebite-dlq
```

## 5. 刪除

先刪 runtime，再刪 base 和 network（runtime 會引用另外兩個 stack 的 export）。base 的 S3 bucket 裡有檔案時無法刪除，要先清空。

```bash
aws cloudformation delete-stack --profile savebite-lab --region us-east-1 --stack-name <stack 名稱>
```

## 6. 異動紀錄

| 日期 | 異動 |
|---|---|
| 2026-11-27 | 建立 `savebite-network`、`savebite-base` |
| 2026-11-27 | 刪除測試用 user pool `User pool - rrletp`（`us-east-1_c1v2XzVOL`），先刪掉它的 domain、關閉刪除保護才刪除 |
| 2026-11-27 | Scheduler + LabRole 驗證：暫時建立 Lambda `savebite-scheduler-test` 和排程 `test-fail-once`、`test-fail-always`（group `savebite`），驗證後全部刪除（Lambda、log group、S3 `test/` 下的 marker），並清空 `savebite-dlq`。結果見 ARCHITECTURE.md §11 |
| 2026-11-27 | 更新 `savebite-base`：新增 S3 部署檔 bucket `savebite-artifacts-126811246350`（其他資源不變） |
| 2026-11-27 | 上傳 `releases/backend-a886d49fc215.tar.gz`（`main` 的 A1 骨架） |
| 2026-11-27 | 建立 `savebite-runtime` 第一段（13:23:41–13:27:56 UTC），測試後刪除（13:31:46–13:34:54 UTC），共開約 11 分鐘，費用約 $0.03 |
| 2026-11-27 | 建立 `savebite-runtime` 第一加第二段（14:29:42–14:43:08 UTC），測試後刪除（15:00:11–15:24:29 UTC），共約 55 分鐘，費用約 $0.18；殘留的 ElastiCache 網路介面與 RDS 自動備份快照在 15:28:54 前由 AWS 自動清除 |

## 7. Scheduler 與 Lambda 的設定方式（已驗證）

之後在 runtime stack 和後端程式要沿用這些設定：

- Scheduler 執行角色：`arn:aws:iam::126811246350:role/LabRole`
- 一次性排程：`ScheduleExpression=at(yyyy-mm-ddThh:mm:ss)`、`ScheduleExpressionTimezone=UTC`、`FlexibleTimeWindow={Mode: OFF}`、`ActionAfterCompletion=DELETE`、`GroupName=savebite`
- 排程 target：`RetryPolicy={MaximumRetryAttempts: 2, MaximumEventAgeInSeconds: 3600}`、`DeadLetterConfig={Arn: <savebite-dlq ARN>}`
- Lambda 非同步設定（`PutFunctionEventInvokeConfig`）：`MaximumRetryAttempts=2`、`MaximumEventAgeInSeconds=3600`、`DestinationConfig.OnFailure.Destination=<savebite-dlq ARN>`
- 函式錯誤由 Lambda 的非同步重試處理，Scheduler 的 retry 只處理投遞失敗

## 8. savebite-runtime

目前模板包含：
- **第一段**：NAT Gateway、ALB、Launch Template、Auto Scaling group（EC2 × 2）
- **第二段**：RDS PostgreSQL 16.13（密碼由 Secrets Manager 管理）、ElastiCache Redis 7.1、Secrets Manager interface endpoint、Lambda `savebite-release`（目前是佔位程式）、每 5 分鐘的 EventBridge rule `savebite-sweep`

監控（第三段）之後再加。合計約 **$0.19／小時**，建立約 13 到 14 分鐘。**用完當天就刪除。**

### 部署步驟

```bash
# 1. 打包已 commit 的 backend/ 並上傳，記下最後一行印出的 AppArtifactKey
scripts/package-backend.sh

# 2. 建立 stack（開發時 NAT 1 個；實驗一、二改成 NatGatewayCount=2）
aws cloudformation create-stack --profile savebite-lab --region us-east-1 \
  --stack-name savebite-runtime \
  --template-body file://infra/cloudformation/runtime.yaml \
  --parameters ParameterKey=AppArtifactKey,ParameterValue=<上一步的 key> \
               ParameterKey=NatGatewayCount,ParameterValue=1 \
  --tags Key=project,Value=savebite
aws cloudformation wait stack-create-complete --profile savebite-lab --region us-east-1 \
  --stack-name savebite-runtime

# 3. 取得 ALB 網址
aws cloudformation describe-stacks --profile savebite-lab --region us-east-1 \
  --stack-name savebite-runtime \
  --query "Stacks[0].Outputs[?OutputKey=='AlbDnsName'].OutputValue" --output text
```

**換新版本**：commit 後重跑 `package-backend.sh`，再用 `update-stack` 把 `AppArtifactKey` 改成新的 key（其他參數用 `UsePreviousValue=true`）。Auto Scaling 會一次換一台，至少保留一台在服務。

**刪除**（每次測完都要做）：

```bash
aws cloudformation delete-stack --profile savebite-lab --region us-east-1 --stack-name savebite-runtime
aws cloudformation wait stack-delete-complete --profile savebite-lab --region us-east-1 --stack-name savebite-runtime
```

### 參數

| 參數 | 預設 | 說明 |
|---|---|---|
| `AppArtifactKey` | （必填） | `package-backend.sh` 印出的 S3 key |
| `NatGatewayCount` | `1` | 實驗一、二改成 `2` |
| `InstanceType` | `t3.small` | 可選 t3.micro／small／medium |
| `AppEnv` | `dev` | 壓測時改成 `loadtest` |
| `RdsMultiAz` | `false` | 實驗二（RDS 容錯移轉）改成 `true`，RDS 費用約加倍 |
| `DbInstanceClass` | `db.t3.micro` | |
| `CacheNodeType` | `cache.t3.micro` | |
| `ReservationHoldMinutes` | `30` | 寫進 EC2 的 `RESERVATION_HOLD_MINUTES` |

### 第二段資源

| 資源 | 名稱 | 設定 |
|---|---|---|
| RDS | `savebite-db` | PostgreSQL 16.13、db.t3.micro、gp3 20 GB、加密、資料子網路、`db-sg`；主帳號 `savebite_admin`，資料庫 `savebite`；`ManageMasterUserPassword`（密碼存在 Secrets Manager）；備份保留 1 天；**刪除 stack 時不留快照** |
| ElastiCache | `savebite-redis` | Redis 7.1、cache.t3.micro、單一節點、資料子網路、`redis-sg` |
| Secrets Manager endpoint | | interface endpoint，資料子網路 A／B，Private DNS 開啟；SG `endpoint-sg`（只接受 `app-sg`、`lambda-sg` 的 443） |
| `lambda-sg` 對外規則 | | runtime stack 加上 443 → `endpoint-sg`（隨 stack 一起刪除） |
| Lambda | `savebite-release` | Python 3.12、LabRole、資料子網路、`lambda-sg`、逾時 30 秒；非同步重試 2 次、失敗送 `savebite-dlq`；log group 保留 7 天 |
| EventBridge rule | `savebite-sweep` | `rate(5 minutes)`，payload `{"type": "sweep"}` |

**為什麼要 Secrets Manager endpoint**：Lambda 在資料子網路，沒有對外路由，連不到 Secrets Manager 取得 DB 密碼。endpoint 約 $0.02／小時，只在 runtime 存在時計費。不把密碼放進 Lambda 環境變數，因為 Console 上看得到明文，而且 RDS 自動換密碼後就會失效。

**Lambda 目前是佔位程式**：只測試 DB、Redis 的 TCP 連線和 Secrets Manager 讀取，不改任何資料。正式的釋出邏輯（ARCHITECTURE.md §6.3）由 A 組員實作後替換，重試、DLQ、觸發規則等設定可以沿用。

**注意：RDS 管理的密碼預設每 7 天自動輪替一次。** EC2 只在開機時讀一次密碼，如果 runtime stack 開超過 7 天（不應該發生），密碼換掉後要重開 EC2。

### EC2 開機流程（user data）

1. `dnf install python3.11 python3.11-pip aws-cfn-bootstrap`
2. 從 artifacts bucket 下載打包檔，解壓到 `/opt/savebite/backend`，建立 venv 並安裝 `requirements.txt`
3. 從 Secrets Manager 取得 RDS 帳密（經 VPC endpoint），URL 編碼後組成 `DATABASE_URL`。這幾行關閉 `set -x`，所以密碼不會進日誌
4. 寫入 `/etc/savebite/env`（權限 640，`root:savebite`），內容包含 `DATABASE_URL`、`REDIS_URL`、Cognito、S3、SNS、Lambda、Scheduler 等 13 個環境變數
5. 建立 systemd 服務 `savebite`（uvicorn，port 8000）
6. 本機 `/health` 回 200 後，用 `cfn-signal` 回報成功；任何一步失敗就回報失敗

除錯：用 Session Manager 連進 EC2（Console → EC2 → 選機器 → Connect → Session Manager），查看：
- 開機日誌：`sudo cat /var/log/savebite-userdata.log`
- 服務狀態與日誌：`systemctl status savebite`、`sudo journalctl -u savebite -n 100`

### 2026-11-27 第一段測試結果

| 項目 | 結果 |
|---|---|
| 建立時間 | 4 分 15 秒（兩台都回報成功才算完成） |
| ALB `/health` | ✅ 200，約 0.45 秒（從台灣連線） |
| EC2 分布 | ✅ us-east-1a、us-east-1b 各一台，target group 都 healthy |
| SSM | ✅ 兩台都 Online，Run Command 可執行 |
| 經 NAT 對外 | ✅ 兩台的對外 IP 都是 NAT 的 EIP（1b 跨 AZ 走 1a 的 NAT）；連 Cognito endpoint 正常 |
| Python | 3.11.18 |
| 終止一台 EC2 | 見下 |

**終止 1a 的 EC2（直接從 EC2 終止，模擬機器故障）**，同時每 0.5 秒打一次 ALB `/health`：

| 時間（UTC） | 事件 |
|---|---|
| 13:29:07 | 終止 `i-0433fb2c7cc03cd09`（1a） |
| 13:29:10–13:29:26 | 6 個請求失敗（3 個 502、3 個 3 秒逾時），**中間的請求仍然成功**（被送到 1b） |
| 13:29:29 | target group 只剩 1b 那台，之後全部成功 |
| 13:30:03 | Auto Scaling 發現機器不見（約 56 秒後） |
| 13:30:05 | 開始啟動新機器 `i-0aa694d9b66d284ad` |
| 13:31:24 | 新機器 healthy，恢復成 2 台 |

- **服務沒有完全中斷**：受影響時間約 19 秒，期間部分請求失敗；整段 147 個請求中有 6 個失敗（4.1%）
- **恢復成 2 台花了 2 分 17 秒**
- 失敗集中在 ALB 還沒判定那台不健康的期間（健康檢查 10 秒一次、連續 2 次失敗才判定）

### 2026-11-27 第二段測試結果

建立：14:29:42–14:43:08 UTC（13 分 26 秒，主要在等 RDS）。

| 項目 | 結果 |
|---|---|
| Learner Lab 支援度 | ✅ ElastiCache、RDS `ManageMasterUserPassword`、Secrets Manager interface endpoint 都能建立 |
| ALB `/health` | ✅ 200 |
| EC2 讀 Secrets Manager | ✅ 兩台開機時都取得密碼並組成 `DATABASE_URL`（經 VPC endpoint） |
| EC2 → RDS | ✅ asyncpg 連線成功，`server_version` 16.13，`savebite_admin@savebite` |
| EC2 → Redis | ✅ `PING` → `+PONG` |
| 環境變數檔 | ✅ 13 個變數齊全，權限 `640 root:savebite`；開機日誌沒有出現密碼 |
| **EC2 PassRole LabRole** | ✅ 在 EC2 上用 LabInstanceProfile 建立以 LabRole 為執行角色的排程成功；14:49:00 排定，14:49:11 觸發 Lambda，執行後自動刪除 |
| Lambda（VPC 內） | ✅ 手動呼叫：連 DB 21 ms、連 Redis 10 ms、Secrets Manager 讀得到密碼 |
| 安全網掃描 rule | ✅ 14:43、14:48、14:53、14:58 各觸發一次，間隔 5 分鐘 |
| DLQ | 0 則（沒有失敗） |

刪除：15:00:11–15:24:29 UTC（**24 分鐘**，比第一段久很多，主要在等 RDS 和 VPC 內 Lambda 的網路介面釋放）。

刪除後檢查殘留：
- RDS、ElastiCache、secret、interface endpoint、`endpoint-sg`、NAT、EIP、EC2、ALB、Lambda、log group 都已刪除；`lambda-sg` 的 443 規則也已移除
- 剛刪完時還看得到 **ElastiCache 的網路介面**和 **RDS 自動備份快照**（`rds:savebite-db-...`，來自備份保留 1 天），兩者都由 AWS 非同步清除，約 4 分鐘後（15:28:54）都消失了，不需要手動處理
- 從建立到刪除完成共約 55 分鐘，費用約 $0.18

**下次刪除後如果還看到這兩樣**：先等 5 到 10 分鐘再查。ElastiCache 的網路介面沒消失前，`redis-sg` 還在使用中，這時刪除 network stack 會失敗。
