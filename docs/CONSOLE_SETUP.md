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
| `savebite-base` | ✅ `CREATE_COMPLETE` | 2026-11-27 | $0（Cognito Essentials 每月 1 萬名活躍使用者內免費） |
| `savebite-runtime` | 尚未建立（程式寫好才建） | | 計費 |

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
