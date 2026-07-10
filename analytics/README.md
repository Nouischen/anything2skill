# Anything2Skill 分析後台（Cloudflare Worker + D1）

收 `../scripts/telemetry.js` 送來的匿名事件，提供 `/admin` 儀表板看：總用戶、總 skill 數、每人幾份、來源類型分布、每日趨勢。
只存匿名計數，不含任何內容/個資。

複製自 course2notes/analytics，改名適配（獨立 D1 資料庫、獨立 Worker，不共用 course2notes 任何資源）。

## 部署
```bash
cd analytics

# 1) 建 D1 資料庫（複製輸出的 database_id 貼進 wrangler.toml）
wrangler d1 create anything2skill

# 2) 建表（本地＋雲端各跑一次；雲端加 --remote）
wrangler d1 execute anything2skill --file=schema.sql --remote

# 3) 設定後台密碼（Basic Auth 用；帳號預設 admin，可另設 ADMIN_USER）
wrangler secret put ADMIN_KEY
# （選用）wrangler secret put ADMIN_USER

# 4) 部署
wrangler deploy
```
部署完會得到一個網址，例如 `https://anything2skill-analytics.<你的帳號>.workers.dev`。

## 接上工具
把上面網址填進 `../config.example.json`（複製成 `config.json`）：
```json
"telemetryEndpoint": "https://anything2skill-analytics.<你的帳號>.workers.dev/event"
```

## 看後台
瀏覽器開 `https://anything2skill-analytics.<你的帳號>.workers.dev/admin`
→ 跳出登入，輸入帳號 `admin`（或你設的 ADMIN_USER）＋ 你設的 ADMIN_KEY。
（也可用一次性連結 `/admin?k=<ADMIN_KEY>`，進來會種 cookie，之後同瀏覽器免帶 k。）

## API
- `POST /event`：body = `{install_id,event,note_count,platform,version,ts}`。嚴格驗證，格式不符直接丟棄（擋開源端點被亂灌）。
  - `install_id` 需符合 `a2s_[a-f0-9]{8,40}`
  - `event` 白名單：`install`、`skills_done`
  - `platform` 白名單：`youtube`、`video`、`course`、`text`、`article`、`other`（非清單一律壓成 other）
- `GET /admin`：Basic Auth 後回傳 HTML 儀表板。

## 防濫用
端點在開源碼裡是公開的，已做：欄位嚴格驗證＋長度/數值上限＋只收白名單事件。若日後被灌水，可在 Cloudflare 後台加 Rate Limiting 規則（依 IP 限流）。

## 本地測試
```bash
wrangler dev
# 另開終端：
curl -X POST http://localhost:8787/event -H "Content-Type: application/json" \
  -d '{"install_id":"a2s_abc123def4567890","event":"skills_done","note_count":3,"platform":"text","version":"1.0.0","ts":1735660800}'
# 開 http://localhost:8787/admin 看
```
