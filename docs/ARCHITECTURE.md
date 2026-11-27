# 惜食地圖：系統架構

雲端平台課程期末專案（三人一組，12/23 繳交）。本文件描述**已定案**的架構與設計，開發時以此為準。

---

## 1. 專案概要

惜食地圖是剩食即時媒合平台。餐廳、麵包店、活動主辦方發布剩下仍可食用的食物（種類、數量、地點、領取時間、價格或免費），附近的人在地圖上查詢並預約領取。

技術重點：
- 很多人同時搶同一份食物時**不能超賣**
- 剩餘份數要**即時**更新到所有正在看的畫面
- 預約後逾時未取，份數要**自動釋出**

## 2. 目標與驗收標準

| 目標 | 標準 | 驗證方式 |
|---|---|---|
| 不超賣 | 1,000 人同時搶 10 份，剛好 10 人成功，超賣 0 次 | k6 壓測，比對成功筆數與最終 `remaining` |
| 即時同步 | 庫存變動推到所有連線，p95 < 1 秒 | 訊息帶 `sent_at`，前端計算延遲 |
| 高可用 | 關掉一整個可用區（AZ），服務不中斷 | 壓測中停掉 AZ-a 的 EC2，量錯誤率與中斷秒數 |

## 3. 環境限制

- **AWS Academy Learner Lab**，Region `us-east-1`，預算約 50 美元。資源建在組長的 Lab 帳號，本機 AWS CLI 一律使用 profile `savebite-lab`（Lab 憑證約 4 小時過期，要從 Lab 頁面 AWS Details 重新複製）
- IAM 通常只能使用 **LabRole**，不能自行建立角色；部分服務或機型可能受限
- **AWS 資源用 CloudFormation 管理**（見 3.1）。不用 Terraform（state 共用麻煩）、CDK／SAM（需要 bootstrap 或自動建立 IAM role，Lab 不允許）
- **已確認不能用：CloudFront、Amazon Location**（權限不足）。已確認可用：Cognito（可建立 user pool）。SQS 在 Lab 支援清單上
- EC2 只能用 nano～large 機型，同時最多 9 台；Lambda 同時最多 10 個執行環境
- RDS 機型限 nano～medium，不支援 Enhanced monitoring（建立時要關閉）
- EC2 掛 **LabInstanceProfile**（才能用 Systems Manager 連線），Lambda 掛 **LabRole**
- 工作階段結束時 EC2 會被停止，下次開 Lab 會**自動重新啟動**；RDS 不會自動停止，要手動停（停 7 天後 AWS 會自動重啟）
- **預算超過整個帳號會被停用、資源全部刪除**；Lab 畫面顯示的剩餘預算每 8–12 小時才更新
- 會常駐計費的資源（NAT Gateway、ALB、RDS、EC2、ElastiCache）全部放在 `savebite-runtime` stack，只在開發和實驗時建立，用完整個 stack 刪除

### 3.1 CloudFormation stack

模板放在 `infra/cloudformation/`，部署步驟與實際建出的 ID 記錄在 `docs/CONSOLE_SETUP.md`。

| Stack | 內容 | 費用 | 生命週期 |
|---|---|---|---|
| `savebite-network` | VPC、6 個子網路、IGW、路由表、S3 Gateway Endpoint、所有 Security Group | 免費 | 常駐 |
| `savebite-base` | Cognito user pool 與 app client、S3 照片 bucket（含 CORS、Lifecycle）、SNS topic、SQS DLQ、Scheduler schedule group | 免費或幾乎免費 | 常駐 |
| `savebite-runtime` | NAT Gateway、ALB、Auto Scaling（EC2）、RDS、ElastiCache、Lambda、安全網掃描的 EventBridge rule | 計費 | 用完就刪 |

`savebite-runtime` 參數：

| 參數 | 預設 | 實驗時 | 說明 |
|---|---|---|---|
| `NatGatewayCount` | `1`（放 AZ-a，兩個 AZ 的應用子網路都走它） | `2`（每個 AZ 一個） | 開發時省一半 NAT 費用；實驗一、二切成 2 |
| `RdsMultiAz` | `false` | `true` | 實驗二（RDS 容錯移轉）需要開啟；開啟後費用約加倍 |

各 stack 之間用 CloudFormation Export／`Fn::ImportValue` 傳遞 ID（例如子網路、SG、路由表、DLQ ARN）。

大約費用（us-east-1，僅供估算，以 Pricing 頁為準）：

| 資源 | 每小時 |
|---|---|
| NAT Gateway | 每個約 $0.045（另計流量） |
| ALB | 約 $0.0225 起（另計 LCU） |
| EC2 t3.small | 每台約 $0.021 |
| RDS db.t3.micro | 單一 AZ 約 $0.017；Multi-AZ 約 $0.034 |
| ElastiCache cache.t3.micro | 約 $0.017 |

---

## 4. 架構總覽

```
使用者瀏覽器
 └─ Internet Gateway ─→ ALB（跨 AZ-a / AZ-b，HTTP）
                          └─→ EC2 × 2（FastAPI：前端靜態檔 + REST API + WebSocket，同一個網址）
                                 ├─→ RDS PostgreSQL（主：AZ-a；實驗時開 Multi-AZ，同步備援在 AZ-b）
                                 ├─↔ ElastiCache Redis（Pub/Sub）
                                 ├─→ S3 照片（經 S3 Gateway Endpoint）
                                 └─→ NAT Gateway ─→ Cognito、SNS、EventBridge Scheduler API、SSM

瀏覽器 ─(presigned URL)─→ S3 照片（直傳、直讀）

EventBridge Scheduler ─(到期)─→ Lambda（VPC 內）─→ RDS、Redis
        └─(投遞失敗)─→ SQS DLQ          └─(執行失敗)─→ SQS DLQ
EventBridge rule（每 5 分鐘，安全網掃描）─→ 同一個 Lambda
```

### 4.1 網路

| 項目 | 設定 |
|---|---|
| VPC | `10.0.0.0/16`，跨 AZ-a、AZ-b |
| 公有子網路 | `10.0.1.0/24`（AZ-a）、`10.0.2.0/24`（AZ-b）：ALB、NAT Gateway |
| 私有應用子網路 | `10.0.11.0/24`（AZ-a）、`10.0.12.0/24`（AZ-b）：EC2，無公有 IP |
| 私有資料子網路 | `10.0.21.0/24`（AZ-a）、`10.0.22.0/24`（AZ-b）：RDS、ElastiCache、Lambda |
| Internet Gateway | 外部流量進入 VPC |
| NAT Gateway | 預設 1 個（AZ-a），實驗時每個 AZ 各一個（`NatGatewayCount`）；私有應用子網路經此呼叫 Cognito、SNS、EventBridge Scheduler API、Systems Manager |
| S3 Gateway Endpoint | 私有子網路直連 S3，不經 NAT |

路由表：
- 公有：`0.0.0.0/0 → IGW`
- 應用 AZ-a／AZ-b：各一張，由 network stack 建立；`0.0.0.0/0 → NAT` 的路由由 runtime stack 加上（`NatGatewayCount=1` 時兩張都指向 AZ-a 的 NAT）
- 資料 AZ-a／AZ-b：只有 local 與 S3 endpoint，**沒有對外路由**（Lambda 只連 DB 與 Redis，不需上網）

注意：**沒有 NAT 時 EC2 無法用 Systems Manager 連線，也無法下載套件**。NAT 和 EC2 同在 runtime stack，一起建、一起刪，所以不會發生 EC2 存在但沒有 NAT 的情況。

### 4.2 服務與用途

| 服務 | 用途 | 重點設定 |
|---|---|---|
| ALB | 入口，轉送 HTTP 與 WebSocket | 跨 2 AZ；只有 HTTP 80 listener；健康檢查 `GET /health`；閒置逾時預設 60 秒 |
| EC2 Auto Scaling | 執行 FastAPI，同時提供前端靜態檔 | **固定 2 台**（最少＝最多＝期望＝2），跨 2 AZ；健康檢查類型 ELB；目的是容錯，不做擴展 |
| RDS PostgreSQL 16 | 主要資料庫 | 預設單一 AZ；`RdsMultiAz=true` 時同步備援、故障自動切換；關閉 Enhanced monitoring |
| ElastiCache Redis | 多台 EC2 之間同步推播 | Pub/Sub；故障時系統降級為輪詢（見 6.5） |
| Lambda | 逾時釋出預約、到期下架貼文、每 5 分鐘安全網掃描 | 掛在 VPC 私有資料子網路；Python；LabRole；非同步呼叫的失敗目的地設為 SQS DLQ |
| EventBridge rule | 每 5 分鐘觸發安全網掃描（見 6.3） | `rate(5 minutes)`；靠 Lambda resource-based policy 觸發，不需要執行角色 |
| EventBridge Scheduler | 每筆預約、每則貼文各建一個一次性排程 | schedule group `savebite`；`ActionAfterCompletion=DELETE`；設重試與 DLQ（SQS）；執行角色 LabRole（**待驗證**，見 11） |
| SQS | Scheduler 與 Lambda 的失敗佇列（DLQ） | 標準佇列；保留 14 天；有訊息時要人工檢查 |
| Cognito | 使用者池，簽發 JWT | 不用 Hosted UI（見 6.8）；public app client（無 client secret）；後端呼叫 Cognito API 登入，API 驗證 JWT 後才放行 |
| S3 | 食物照片 | 私有 bucket；照片用 presigned URL 由前端直傳、直讀；設 CORS；Lifecycle 清除舊照片（見 6.10） |
| SNS | 新貼文 Email 通知訂閱者 | 每個訂閱用 filter policy 依 `geohash5`（和 `food_type`）過濾（見 6.9）；經 NAT 呼叫 |
| CloudWatch | 日誌、監控、告警 | |
| Cost Explorer | 追蹤花費 | Lab 畫面的預算數字有延遲，要自己常看 |
| Systems Manager | 連線管理 EC2 | 不開 SSH、不放跳板機；EC2 要掛 LabInstanceProfile；需要 NAT |

前端（React 打包後的靜態檔）由 FastAPI 一起提供，和 API 同一個網址，所以前端呼叫 API 沒有跨網域（CORS）和 HTTPS 混合內容的問題。例外是照片直傳 S3，屬於跨網域請求，要在 bucket 設 CORS（見 6.10）。店家位置由提供者在地圖上點選（前端用 Leaflet + OpenStreetMap 圖磚），不需要地址轉座標服務；地址由提供者手動輸入。

### 4.3 Security Group（每一層只接受上一層的流量）

| SG | 允許進入 | 來源 |
|---|---|---|
| `alb-sg` | 80 | `0.0.0.0/0`（沒有憑證，不開 443） |
| `app-sg` | 8000（FastAPI） | 只限 `alb-sg` |
| `db-sg` | 5432 | 只限 `app-sg`、`lambda-sg` |
| `redis-sg` | 6379 | 只限 `app-sg`、`lambda-sg` |
| `lambda-sg` | 不開放進入 | 只對外連 DB、Redis |

---

## 5. 資料模型（PostgreSQL）

RDS 只存業務資料。照片在 S3（DB 只存 key）、帳密在 Cognito、WebSocket 連線在各台 EC2 記憶體、逾時排程在 EventBridge Scheduler。

```sql
CREATE TABLE users (
  id            UUID PRIMARY KEY,               -- Cognito sub
  display_name  TEXT NOT NULL,
  email         TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE stores (
  id             BIGSERIAL PRIMARY KEY,
  owner_user_id  UUID REFERENCES users(id),     -- 開放資料匯入的店家為 NULL
  source         TEXT NOT NULL CHECK (source IN ('open_data', 'user')),
  source_ref     TEXT,                          -- 開放資料原始 ID
  name           TEXT NOT NULL,
  category       TEXT,
  address        TEXT NOT NULL,                 -- 提供者手動輸入（沒有地址轉座標）
  lat            DOUBLE PRECISION NOT NULL,
  lng            DOUBLE PRECISION NOT NULL,
  geohash5       TEXT NOT NULL,                 -- 推播頻道與 SNS 過濾用，約 5 公里一格
  phone          TEXT,
  opening_hours  TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source, source_ref)
);
CREATE INDEX stores_lat_lng_idx ON stores (lat, lng);

CREATE TABLE listings (
  id              BIGSERIAL PRIMARY KEY,
  store_id        BIGINT NOT NULL REFERENCES stores(id),
  title           TEXT NOT NULL,
  food_type       TEXT NOT NULL,
  description     TEXT,
  photo_key       TEXT,                         -- S3 object key
  quantity_total  INT NOT NULL CHECK (quantity_total > 0),
  remaining       INT NOT NULL CHECK (remaining >= 0 AND remaining <= quantity_total),
  price           INT NOT NULL DEFAULT 0 CHECK (price >= 0),
  original_price  INT,
  pickup_start    TIMESTAMPTZ NOT NULL,
  pickup_end      TIMESTAMPTZ NOT NULL CHECK (pickup_end > pickup_start),
  conditions      TEXT,
  status          TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active', 'sold_out', 'expired', 'withdrawn')),
  version         INT NOT NULL DEFAULT 1,       -- 每次變動 +1，前端丟棄舊訊息用
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX listings_status_end_idx ON listings (status, pickup_end);

CREATE TABLE reservations (
  id           BIGSERIAL PRIMARY KEY,
  listing_id   BIGINT NOT NULL REFERENCES listings(id),
  user_id      UUID NOT NULL REFERENCES users(id),
  qty          INT NOT NULL CHECK (qty > 0),
  status       TEXT NOT NULL DEFAULT 'held'
               CHECK (status IN ('held', 'picked_up', 'released', 'cancelled')),
  pickup_code  TEXT NOT NULL,
  hold_until   TIMESTAMPTZ NOT NULL,            -- 不超過貼文的 pickup_end（見 6.1）
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 同一人對同一則貼文只能有一筆有效預約（取消或釋出後可再預約）
CREATE UNIQUE INDEX reservations_one_active_idx
  ON reservations (listing_id, user_id) WHERE status IN ('held', 'picked_up');
-- 安全網掃描用（見 6.3）
CREATE INDEX reservations_held_until_idx
  ON reservations (hold_until) WHERE status = 'held';

CREATE TABLE subscriptions (
  id                    BIGSERIAL PRIMARY KEY,
  user_id               UUID NOT NULL UNIQUE REFERENCES users(id),  -- 每人一筆（見 6.9）
  lat                   DOUBLE PRECISION NOT NULL,
  lng                   DOUBLE PRECISION NOT NULL,
  radius_km             NUMERIC(4,1) NOT NULL DEFAULT 2.0
                        CHECK (radius_km > 0 AND radius_km <= 5.0),
  food_types            TEXT[],                 -- NULL 表示全部
  geohash5_cells        TEXT[] NOT NULL,        -- 涵蓋半徑的 geohash5 格子，寫進 SNS filter policy
  sns_subscription_arn  TEXT,                   -- 使用者點確認信前為 'pending confirmation'
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**`users` 的寫入時機**：不在註冊時寫入（使用者可能註冊後沒有確認）。每個需要登入的 API 在驗證 JWT 後，從 token 取 `sub`、`email`、`name` 做 upsert（`INSERT ... ON CONFLICT (id) DO UPDATE`）。為了避免每個請求都寫 DB，每台 EC2 在記憶體快取「已 upsert 過的 sub」。

店家初始資料：從交通部觀光署「餐飲 – 觀光資訊資料庫」（政府資料開放平台或 TDX）下載，匯入 `stores`（`source = 'open_data'`）。貼文與預約為程式生成的模擬資料。壓測需要的 1,000 個使用者由腳本直接寫入 `users`（不經 Cognito，見 7.1）。

---

## 6. 核心流程

排程名稱固定為 `reservation-{id}`、`listing-{id}`（放在 schedule group `savebite`）。名稱固定的好處：重複建立會收到 `ConflictException`（視為成功），取消、修改時也能直接用名稱刪除或更新。

### 6.1 預約（防超賣）

**一定要用條件 UPDATE，判斷與扣除在同一個 SQL 內完成。不可先 SELECT 再 UPDATE。**

```sql
BEGIN;

UPDATE listings l
SET remaining  = l.remaining - :qty,
    status     = CASE WHEN l.remaining - :qty = 0 THEN 'sold_out' ELSE l.status END,
    version    = l.version + 1,
    updated_at = now()
FROM stores s
WHERE l.id = :listing_id
  AND s.id = l.store_id
  AND l.status = 'active'
  AND l.remaining >= :qty
  AND now() < l.pickup_end
RETURNING l.remaining, l.status, l.version, l.pickup_end, s.geohash5;
-- 0 列 → ROLLBACK，回 409（已搶完或已過期）

INSERT INTO reservations (listing_id, user_id, qty, pickup_code, hold_until)
VALUES (:listing_id, :user_id, :qty, :pickup_code,
        LEAST(now() + :hold_interval, :pickup_end))   -- 保留時間不超過領取截止
RETURNING id, hold_until;
-- 違反 reservations_one_active_idx → ROLLBACK，回 409（已預約過）

COMMIT;
```

- `SET` 裡的 `l.remaining` 是更新前的值，所以 `l.remaining - :qty = 0` 表示這次扣完剛好歸零。
- 同一個交易內 `now()` 是固定值，所以 UPDATE 和 INSERT 用的是同一個時間點。
- `:qty` 在 API 層先檢查範圍（1 ≤ qty ≤ 每人上限，上限待定）。

COMMIT 之後才做：
1. 建立 EventBridge Scheduler 一次性排程 `reservation-{id}`，**時間＝`hold_until + 1 分鐘`**（避免時鐘誤差讓 Lambda 比 `hold_until` 早觸發），目標＝釋出 Lambda，payload `{"reservation_id": ...}`。失敗重試 3 次，仍失敗就記錄 ERROR，之後由安全網掃描補上（見 6.3）。
2. 發布庫存變動到 Redis（見 6.4）。**Redis 失敗只記錄，不能讓 API 回錯誤。**

保留時間由環境變數 `RESERVATION_HOLD_MINUTES` 設定（預設 30，待定）。

### 6.2 領取與取消

**領取**：店家輸入取餐碼核銷，只有該店家的擁有者可以核銷，而且要在保留時間內。

```sql
UPDATE reservations r
SET status = 'picked_up', updated_at = now()
FROM listings l, stores s
WHERE r.id = :id
  AND r.pickup_code = :code
  AND r.status = 'held'
  AND now() < r.hold_until               -- hold_until 已不超過 pickup_end
  AND l.id = r.listing_id
  AND s.id = l.store_id
  AND s.owner_user_id = :me
RETURNING r.id;
-- 0 列 → 回 409（取餐碼錯誤、已逾時、已領取或不是你的店）
```

**取消**：使用者取消自己的預約。**不能沿用 6.3 的 SQL**，因為 6.3 有 `hold_until <= now()` 條件，在保留時間內取消會更新到 0 列。

```sql
BEGIN;

UPDATE reservations
SET status = 'cancelled', updated_at = now()
WHERE id = :id AND user_id = :me AND status = 'held'
RETURNING listing_id, qty;
-- 0 列 → ROLLBACK，回 409（已領取、已釋出、已取消，或不是你的預約）

UPDATE listings l
SET remaining  = l.remaining + :qty,
    status     = CASE WHEN l.status = 'sold_out' AND now() < l.pickup_end THEN 'active' ELSE l.status END,
    version    = l.version + 1,
    updated_at = now()
FROM stores s
WHERE l.id = :listing_id AND s.id = l.store_id
RETURNING l.remaining, l.status, l.version, s.geohash5;

COMMIT;
```

COMMIT 後：刪除排程 `reservation-{id}`（失敗只記錄；就算沒刪掉，Lambda 也會因為 `status = 'held'` 不成立而不做事），再發布到 Redis。領取成功後同樣刪除排程。

### 6.3 逾時釋出（Lambda，必須冪等）

同一筆預約的 Lambda 可能被重試或重複觸發，靠 `status = 'held'` 條件確保只加回一次：

```sql
BEGIN;

UPDATE reservations
SET status = 'released', updated_at = now()
WHERE id = :reservation_id AND status = 'held' AND hold_until <= now()
RETURNING listing_id, qty;

UPDATE listings l
SET remaining  = l.remaining + :qty,
    status     = CASE WHEN l.status = 'sold_out' AND now() < l.pickup_end THEN 'active' ELSE l.status END,
    version    = l.version + 1,
    updated_at = now()
FROM stores s
WHERE l.id = :listing_id AND s.id = l.store_id
RETURNING l.remaining, l.status, l.version, s.geohash5;

COMMIT;
```

**第一個 UPDATE 回 0 列時，不能直接結束**，要先判斷原因：

```sql
SELECT status, hold_until FROM reservations WHERE id = :reservation_id;
```

- `status <> 'held'`（已領取、已取消、已釋出）→ 正常結束
- `status = 'held'` 且 `hold_until > now()`（排程提早觸發）→ **丟出例外**，讓 Lambda 的非同步重試機制約 1 分鐘後再執行一次。若直接回報成功，就不會再重試，份數會永遠卡住
- 查無此筆 → 記錄 WARNING 後結束

COMMIT 後發布變動到 Redis（失敗不影響釋出，前端輪詢或下次推送會更新）。

已過期或已下架的貼文被加回份數時，`status` 維持 `expired`／`withdrawn`，不會變回 `active`。

**貼文到期下架**：每則貼文在 `pickup_end + 1 分鐘` 建排程 `listing-{id}`，Lambda 執行：

```sql
UPDATE listings l
SET status = 'expired', version = l.version + 1, updated_at = now()
FROM stores s
WHERE l.id = :id
  AND s.id = l.store_id
  AND l.status IN ('active', 'sold_out')
  AND l.pickup_end <= now()
RETURNING l.remaining, l.status, l.version, s.geohash5;
```

0 列時同樣先查原因：已是 `expired`／`withdrawn` → 結束；仍是 `active`／`sold_out` 且 `pickup_end` 在 5 分鐘內 → 丟出例外重試；`pickup_end` 更晚（已被 PATCH 延後，新排程會另外觸發）→ 結束。成功後發布變動。

**重試與失敗佇列**（2026-11-27 實測驗證，見 11）：
- Scheduler 用**非同步**方式呼叫 Lambda：只要 Lambda 接受了這次呼叫，Scheduler 就算投遞成功。**函式丟出的例外不會觸發 Scheduler 重試**
- **函式錯誤由 Lambda 的非同步重試負責**：設定 `MaximumRetryAttempts=2`、`MaximumEventAgeInSeconds=3600`。重試沿用同一個 request ID，間隔約 1 分鐘、2 分鐘，總共最多執行 3 次。用完後由 Lambda 的失敗目的地（on-failure destination）送到 SQS DLQ，訊息內容是 `requestContext.condition = "RetriesExhausted"`，加上原本的 payload 和錯誤訊息
- Scheduler 的 retry policy 和 DLQ 只處理**投遞失敗**（例如權限錯誤、Lambda 不存在、呼叫被拒），還是要設定
- 「提早觸發時丟出例外，約 1 分鐘後重試」的做法實測可行
- 實測觸發時間比排定時間晚 12 到 26 秒（`FlexibleTimeWindow=OFF`），沒有觀察到提早觸發，但排程仍維持延後 1 分鐘的保險
- Learner Lab 的 Lambda 最多同時 10 個執行環境，大量預約同時到期時會被限流。非同步呼叫被限流時，Lambda 會把事件留在內部佇列自行重試（在 `MaximumEventAgeInSeconds` 內），再不行就由安全網掃描補上

**安全網掃描（每 5 分鐘）**：用一個 EventBridge rule（`rate(5 minutes)`）觸發同一個 Lambda，payload `{"type": "sweep"}`。
- 用途一：補救排程沒建成、重試用完、訊息進了 DLQ 等情況，確保預約最終一定會被釋出
- 用途二：Scheduler + LabRole 不能用時的**退路**。這時不建立個別排程，完全靠掃描，逾時釋出最多延遲約 10 分鐘（5 分鐘寬限加上 5 分鐘間隔）
- 用 EventBridge rule 而不是 Scheduler，因為 rule 觸發 Lambda 靠的是 Lambda 的 resource-based policy（`AWS::Lambda::Permission`），**不需要執行角色**，不受 LabRole 問題影響
- 掃描條件：

  ```sql
  SELECT id FROM reservations
  WHERE status = 'held' AND hold_until <= now() - interval '5 minutes'
  ORDER BY hold_until
  LIMIT 500;
  ```

  每一筆交給與上面**完全相同的冪等釋出邏輯**（每筆各自一個交易）。這裡的 SELECT 只用來找出候選，真正的判斷仍在 `WHERE status = 'held' AND hold_until <= now()` 的條件 UPDATE 裡，所以和個別排程同時處理同一筆也不會加錯份數
- 預留 5 分鐘寬限，讓正常的個別排程（`hold_until + 1 分鐘`）和它的重試先處理，掃描只撿漏掉的
- 同樣的掃描也處理到期下架：`status IN ('active', 'sold_out') AND pickup_end <= now() - interval '5 minutes'`，交給到期下架的冪等 UPDATE。退路情境下貼文才會下架
- 一次最多 500 筆，剩下的留給下一輪，避免單次執行逾時

Lambda 的 PostgreSQL 驅動：`psycopg` 有二進位檔，打包麻煩，可以考慮純 Python 的 `pg8000`，實作時再決定。

### 6.4 即時推送（WebSocket + Redis Pub/Sub）

- **只有登入的使用者能收推送**。瀏覽器的 WebSocket 不能帶 `Authorization` header，所以連線後的**第一則訊息**必須是 `{"type": "auth", "token": "<id_token>"}`。驗證通過才接受 `subscribe`；5 秒內沒送或驗證失敗就關閉連線（close code `4401`）。token 過期不中斷現有連線，重連時才重新驗證
- 未登入的使用者用輪詢更新地圖（`GET /listings`，間隔 10 秒加隨機抖動，待定）
- 頻道：`area:{geohash5}`。geohash5 每格約 5 公里，使用者在格子邊緣時要一併訂閱相鄰格子，由前端依地圖可視範圍算出要訂閱的格子（上限待定，例如 25 格）
- 訊息格式：
  ```json
  {"type": "listing_update", "listing_id": 123, "remaining": 4,
   "status": "active", "version": 17, "sent_at": "2026-12-01T12:00:00.123Z"}
  ```
- 流程：EC2 或 Lambda 發布 → 每台 EC2 訂閱有連線需要的頻道 → 推給連在自己身上、關注該區域的 WebSocket 連線
- 發布端從 UPDATE 的 `RETURNING s.geohash5` 取得頻道（見 6.1–6.3 的 `UPDATE ... FROM stores`）
- **發布要設短逾時**（例如 200 ms）。連續失敗時暫停嘗試一段時間（例如 30 秒，circuit breaker），避免 Redis 卡住時拖慢 API
- 前端：每則貼文只接受 `version` 比目前大的訊息
- 心跳：每 30 秒互傳一次（小於 ALB 閒置逾時 60 秒）
- 斷線重連成功後，先呼叫 API 重新抓最新份數，補上斷線期間的變動

### 6.5 降級模式（Redis 故障）

Redis 只負責推送，不負責正確性。預約路徑（ALB → EC2 → RDS）完全不經過 Redis。

| | 正常模式 | 降級模式 |
|---|---|---|
| 畫面更新 | WebSocket 主動推送 | 前端每 5 秒呼叫 API |
| 資料來源 | Redis 轉發 | API 直接查 RDS |
| 延遲 | < 1 秒 | 約 5 秒 |
| 預約正確性 | RDS 保證 | RDS 保證 |

切換：
1. EC2 連不上 Redis → 透過 WebSocket 送 `{"type": "mode", "mode": "polling", "interval": 5}`；WebSocket 重連多次失敗時前端也自動切換
2. 前端輪詢，間隔加隨機抖動，避免同時打進來
3. Redis 恢復 → 送 `{"type": "mode", "mode": "push"}`，前端停止輪詢，並**先重抓一次資料**，補上切換期間的變動

### 6.6 附近查詢

先用經緯度範圍（bounding box）篩 `stores`，再計算距離排序，只回傳 `status = 'active'` 且未過期的貼文。之後有需要可在 RDS 啟用 PostGIS。這個 API **不需要登入**。

### 6.7 健康檢查

`GET /health` **只確認程式本身活著，不檢查 RDS 或 Redis**。如果健康檢查依賴外部服務，Redis 或 RDS 一故障，兩台 EC2 會同時被判定不健康並被替換，反而造成全面中斷。

同樣的理由，**程式啟動時連不上 RDS 或 Redis 也不能結束**：連線池在用到時才建立連線，連不上只影響個別請求。否則 RDS 容錯移轉期間剛好重啟的 EC2 會起不來，然後被 Auto Scaling 反覆替換。

### 6.8 登入（Cognito，不用 Hosted UI）

Cognito Hosted UI 的回呼網址必須是 HTTPS（localhost 除外），我們只有 HTTP，所以不用 Hosted UI：
- App client 是 **public client、沒有 client secret**（不用算 `SECRET_HASH`），開啟 `ALLOW_USER_PASSWORD_AUTH`、`ALLOW_REFRESH_TOKEN_AUTH`
- 註冊：`/auth/signup` → 後端呼叫 `SignUp`，Cognito 寄 email 驗證碼
- 確認：`/auth/confirm` → 後端呼叫 `ConfirmSignUp`
- 登入：`/auth/login` → 後端呼叫 `InitiateAuth`（`USER_PASSWORD_AUTH`），取得 JWT 回傳給前端
- 之後每個需要登入的請求帶 `Authorization: Bearer <id_token>`，後端用 Cognito JWKS 驗簽，並檢查 `iss`、`aud`（＝app client ID）、`token_use = id`、是否過期。JWKS 快取在記憶體
- `SignUp`、`ConfirmSignUp`、`InitiateAuth` 不需要 AWS 憑證，所以本機開發只要有 user pool ID 和 client ID 就能登入
- Cognito 內建的寄信服務每天大約只能寄 50 封，測試時不要大量註冊

### 6.9 新貼文 Email 通知（SNS filter policy）

一個 SNS topic 會寄給所有訂閱者，所以用**每個訂閱各自的 filter policy** 依區域過濾：

1. `POST /subscriptions`：後端算出涵蓋 `(lat, lng, radius_km)` 的 geohash5 格子（半徑上限 5 公里，最多約 9 格），寫入 `subscriptions.geohash5_cells`
2. 後端呼叫 SNS `Subscribe`（`Protocol=email`、`ReturnSubscriptionArn=true`），`FilterPolicyScope=MessageAttributes`，filter policy 例如：
   ```json
   {"geohash5": ["wsqqm", "wsqqk", "..."], "food_type": ["bread", "bento"]}
   ```
   `food_types` 為 NULL 時不放 `food_type` 這個鍵。SNS 規定 filter policy 的值組合總數不能超過 150（格子數 × 種類數），所以要限制種類數量
3. 使用者要自己點 SNS 寄出的確認信，訂閱才生效
4. 發布新貼文時，`Publish` 帶 message attributes `geohash5`（店家所在格子）與 `food_type`
5. 每位使用者只有一筆訂閱（`user_id UNIQUE`）。同一個 email 重複訂閱同一個 topic 會沿用原本的訂閱，所以修改時用 `SetSubscriptionAttributes` 更新 filter policy，不要重新訂閱

格子是近似範圍，可能會收到稍微超出半徑的通知，信件內容附上距離即可。

### 6.10 照片（S3 presigned URL）

- Bucket 私有，開啟 Block Public Access
- 上傳：`POST /uploads/presign` 回傳 presigned PUT URL（有效 5 分鐘，限定 `Content-Type` 為圖片），key 為 `photos/{uuid}.{ext}`；前端直接 PUT 到 S3
- 顯示：API 回傳貼文時附 presigned GET URL（有效 1 小時）
- CORS：允許 `PUT`、`GET`。**開發期**的 `AllowedOrigins` 先設 `*`，因為 presigned URL 本身就是授權，而且 ALB 網址在 runtime stack 建立前還不知道。**runtime stack 建好、知道 ALB 網址後，要改成只允許 `http://<ALB DNS 名稱>`、`http://localhost:5173`、`http://localhost:8000`**（base stack 參數 `PhotoCorsOrigins`，更新 stack 即可）
- Lifecycle：`photos/` 下的物件 30 天後刪除；未完成的 multipart upload 1 天後清除
- 本機開發產生 presigned URL 需要 Lab 憑證（`AWS_PROFILE=savebite-lab`），憑證過期後 URL 也會失效

### 6.11 修改與下架貼文（預設規則，可再調整）

- **份數**：用條件 UPDATE 同時調整 `quantity_total` 與 `remaining`：`SET quantity_total = quantity_total + :delta, remaining = remaining + :delta ... WHERE remaining + :delta >= 0`，並重新計算 `status`（`active`／`sold_out`）。不能減到比已預約的量還少
- **`pickup_end`**：只能延後、不能提前（避免已預約的 `hold_until` 超過新的截止時間），延後時用 `UpdateSchedule` 更新 `listing-{id}`
- **下架**（`status = 'withdrawn'`）：不能再被預約，已經 `held` 的預約保留，使用者仍可在 `hold_until` 前領取
- 每次修改都 `version + 1` 並發布到 Redis

### 6.12 連線數

db.t3.micro 的 `max_connections` 大約在 80 上下。每台 EC2 的連線池上限 10（`DB_POOL_MAX_SIZE`），Lambda 最多 10 個執行環境、每個 1 條連線，合計約 30 條，有足夠餘裕。1,000 人同時預約時，請求會在連線池排隊，同一列的 UPDATE 本來就會被列鎖串行化。

---

## 7. API 草案

| 方法 | 路徑 | 說明 | 需要登入 |
|---|---|---|---|
| GET | `/health` | 健康檢查 | 否 |
| POST | `/auth/signup` | 註冊（後端呼叫 Cognito `SignUp`） | 否 |
| POST | `/auth/confirm` | 輸入 email 驗證碼（`ConfirmSignUp`） | 否 |
| POST | `/auth/login` | 登入（`InitiateAuth`），回傳 JWT | 否 |
| GET | `/listings?lat=&lng=&radius_km=&food_type=` | 附近的貼文 | 否 |
| GET | `/listings/{id}` | 貼文詳情 | 否 |
| POST | `/stores` | 註冊店家（提供者），經緯度由地圖點選 | 是 |
| POST | `/listings` | 發布貼文（店家擁有者） | 是 |
| PATCH | `/listings/{id}` | 修改或下架（店家擁有者，見 6.11） | 是 |
| POST | `/listings/{id}/reservations` | 預約 `{qty}` → 201 或 409 | 是 |
| DELETE | `/reservations/{id}` | 取消自己的預約 | 是 |
| POST | `/reservations/{id}/pickup` | 店家核銷 `{pickup_code}` | 是 |
| GET | `/me/reservations` | 我的預約 | 是 |
| POST | `/uploads/presign` | 取得照片上傳用 presigned URL | 是 |
| POST | `/subscriptions` | 訂閱區域通知（見 6.9） | 是 |
| WS | `/ws` | 即時推送；第一則訊息 `auth`，之後 `{"type": "subscribe", "areas": [...]}` | 是（見 6.4） |

前端靜態檔不需登入。需要登入的 API 由 FastAPI dependency 驗證 JWT（見 6.8），並 upsert `users`（見第 5 節）。沒有獨立的「提供者」角色：誰擁有店家（`stores.owner_user_id`），誰就能為該店發布、修改貼文和核銷。

### 7.1 壓測登入

- 只在 `APP_ENV=loadtest` 時啟用：請求帶 `X-Loadtest-User-Id: <uuid>`，後端直接當成該使用者，不驗證 JWT
- 其他環境一律忽略這個 header（並記錄 WARNING）
- 壓測用的使用者由 `scripts/` 的腳本預先寫入 `users`，不經 Cognito（Cognito `InitiateAuth` 有速率上限，也不需要真的登入 1,000 次）

---

## 8. 程式與設定

### 8.1 技術選擇

- 後端：Python 3.11 + FastAPI（REST 與 WebSocket），PostgreSQL 驅動與 Redis 客戶端使用 asyncio 版本
- Lambda：Python
- 前端：React，打包後由 FastAPI 提供靜態檔；地圖用 Leaflet + OpenStreetMap
- 基礎設施：CloudFormation（YAML）
- 壓測：k6

### 8.2 建議目錄結構（實際以 repo 為準）

```
frontend/                 React
backend/                  FastAPI（routers、services、db、realtime）
lambda/release/           逾時釋出與到期下架
infra/cloudformation/     network.yaml、base.yaml、runtime.yaml
load-tests/               k6 腳本
scripts/                  部署腳本、開放資料匯入、模擬資料生成
docs/                     本文件、CONSOLE_SETUP.md
```

### 8.3 環境變數

設定值一律放環境變數，不寫死在程式碼，也不提交到 git。

`DATABASE_URL`、`DB_POOL_MAX_SIZE`、`REDIS_URL`、`AWS_REGION`（us-east-1）、`COGNITO_USER_POOL_ID`、`COGNITO_APP_CLIENT_ID`、`PHOTO_BUCKET`、`SNS_TOPIC_ARN`、`RELEASE_LAMBDA_ARN`、`SCHEDULER_ROLE_ARN`、`SCHEDULER_GROUP`、`SCHEDULER_DLQ_ARN`、`RESERVATION_HOLD_MINUTES`、`APP_ENV`

本機開發另外設 `AWS_PROFILE=savebite-lab`（只有 S3、SNS、Scheduler 需要；EC2 上用 LabInstanceProfile，不設這個變數）。

壓測用的測試登入只能在 `APP_ENV=loadtest` 時啟用（見 7.1）。

---

## 9. 實驗

1. **故障恢復：運算層**：壓測中終止一台 EC2，再停掉整個 AZ-a；量錯誤率、中斷秒數、機器補回時間。**runtime stack 要設 `NatGatewayCount=2`**，否則 AZ-a 的 NAT 是單點故障
2. **故障恢復：資料層**：RDS 容錯移轉；停掉 Redis 觀察降級；量中斷秒數、超賣次數、推送延遲。**要設 `RdsMultiAz=true`**（現有執行個體改成 Multi-AZ 要等一段時間，建議實驗前提早切換），`NatGatewayCount=2`
3. **效能與正確性**：1 台 vs. 2 台吞吐量；天真寫法（先 SELECT 再 UPDATE）vs. 條件 UPDATE 的超賣次數。天真寫法只用於這個實驗，需另外的測試表或暫時拿掉 `remaining >= 0` 的 CHECK，才會真的出現超賣
4. **成本分析**：本方案 vs. 全 Serverless 方案（Pricing Calculator 估算、Cost Explorer 實測）；比較 NAT 1 個 vs. 2 個、RDS 單一 AZ vs. Multi-AZ 的成本差異

## 10. 分工

- A 資料與交易：資料表、預約交易、逾時釋出 Lambda、壓測
- B 應用與即時：FastAPI、WebSocket、Redis、SNS
- C 網路與基礎設施：CloudFormation 模板（network、base、runtime）、ALB、Auto Scaling、監控

## 11. 待確認事項

- ~~**EventBridge Scheduler + LabRole**~~ ✅ **2026-11-27 已驗證可用**
  - LabRole 的 trust policy 包含 `scheduler.amazonaws.com`（也包含 `events.amazonaws.com`）
  - 用 voclabs 身分建立以 LabRole 為執行角色的排程：成功，排程也確實觸發了 Lambda
  - **還沒驗證**：EC2（LabInstanceProfile）呼叫 `CreateSchedule` 時能否 `iam:PassRole` LabRole，要等 runtime stack 建好，在 EC2 上測
  - 不需要走退路；安全網掃描照樣保留，用來補救
- ~~**重試由哪一層負責**~~ ✅ **2026-11-27 已驗證**：由 **Lambda 的非同步重試**負責，結論已寫進 6.3
  - 方法：測試 Lambda 設非同步 `MaximumRetryAttempts=2`，失敗目的地是 `savebite-dlq`；排程設 retry 2 次、DLQ 也是 `savebite-dlq`。兩個排程在同一時間觸發：`fail-once` 第一次丟例外、之後成功；`fail-always` 每次都丟例外。從 CloudWatch Logs 計算執行次數、間隔和 request ID
  - `fail-once`：10:48:26 失敗 → 10:49:24 重試成功（同一個 request ID）
  - `fail-always`：10:48:12、10:49:19、10:51:34 共執行 3 次（同一個 request ID，間隔約 1 分鐘、2 分鐘）→ DLQ 收到 1 則 Lambda 失敗目的地的訊息（`condition = RetriesExhausted`、`approximateInvokeCount = 3`）
  - 判斷：request ID 不變而且次數等於 Lambda 的設定，代表是 Lambda 在重試；Scheduler 沒有額外重試（Scheduler 重試的話 request ID 會換新）
  - 一次性排程設了 `ActionAfterCompletion=DELETE`，執行完確實自動刪除
- **ElastiCache**：Learner Lab 實際建立時是否可用
- **只有 HTTP**：Learner Lab 不能註冊網域，ALB 沒有正式憑證，只能用 HTTP，登入密碼以明文傳輸。課程專案可接受，報告中要列為已知限制
- 預約保留時間（目前預設 30 分鐘）、每人每次預約上限、未登入輪詢間隔、WebSocket 訂閱格子上限
