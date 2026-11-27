import os
from pathlib import Path

# 匯入 app.main 時會讀取設定，缺少 DATABASE_URL 會直接報錯。
# 只在「沒有環境變數也沒有 .env」時才給一個預設值。
# 注意：環境變數的優先順序高於 .env，所以不能無條件設定，否則會蓋掉 .env 裡的真實值。
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
if "DATABASE_URL" not in os.environ and not _ENV_FILE.exists():
    os.environ["DATABASE_URL"] = "postgresql://savebite@127.0.0.1:5432/savebite"
