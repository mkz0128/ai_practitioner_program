# Backend

後端完整說明請看專案根目錄的 [README.md](../README.md)。

本資料夾包含 FastAPI、OpenAI Agents SDK、DuckDB 唯讀查詢、SQL Guardrail、會員方案與測試。

建議使用 Docker 啟動：

```powershell
cd ..
Copy-Item .env.example .env
docker compose up --build -d
```

API 入口：

- `POST /api/chat`
- `GET /api/me`
- `GET /health`

API Key 與會員 token 只放在根目錄 `.env`，不要提交到 GitHub。
