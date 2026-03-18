# 06 — GitHub Actions IP 封鎖解決方案比較分析

## 背景

GitHub Actions 運行在雲端 IP 上，YouTube 會封鎖來自雲端供應商（AWS、GCP、Azure 等）的請求，導致：

- **youtube-transcript-api**：`YouTube is blocking requests from your IP`
- **yt-dlp（Whisper fallback）**：`Sign in to confirm you're not a bot`

結果是所有字幕擷取全部失敗（YouTube 字幕：0 支、Whisper：0 支），AI 分析只能退化為僅依靠 metadata（標題、頻道、觀看數），品質大幅降低。

---

## 方案 1：使用 Proxy 繞過 IP 封鎖

### 原理

透過代理伺服器轉發請求，讓 YouTube 看到的不是 GitHub Actions 的雲端 IP。

### 需要改動的地方

| 檔案 | 改動內容 | 幅度 |
|------|----------|------|
| `config.yml` | 新增 `proxy` 設定欄位 | ~3 行 |
| `src/config.py` | 讀取 proxy 設定 | ~2 行 |
| `src/transcript.py` — `_fetch_youtube_transcript()` | 傳入 proxy 參數給 `YouTubeTranscriptApi` | ~5 行 |
| `src/transcript.py` — `_download_audio()` | yt-dlp 增加 `proxy` 選項 | ~3 行 |
| GitHub Actions Secrets | 新增 `PROXY_URL` 環境變數 | 1 處 |

**總改動量：約 15 行程式碼**

### 程式碼改動概念

- `youtube-transcript-api` v1.x 支援透過 `fetch()` 傳入 proxy：
  ```python
  ytt_api.fetch(video_id, languages=langs, proxies={"https": proxy_url})
  ```
- `yt-dlp` 原生支援 proxy 選項，加入 `info_opts` 和 `dl_opts`：
  ```python
  info_opts = {"quiet": True, "no_warnings": True, "skip_download": True, "proxy": proxy_url}
  dl_opts = {"format": "bestaudio[ext=m4a]/bestaudio/best", ..., "proxy": proxy_url}
  ```

### 費用

| 代理類型 | 月費 | 效果 | 穩定性 |
|----------|------|------|--------|
| 免費代理 | $0 | 差 | 極不穩定，常被二次封鎖，不建議用於 CI |
| 資料中心代理 (Datacenter) | ~$1–5 USD | 中等 | 仍可能被 YouTube 封鎖 |
| **住宅型代理 (Residential)** | **~$5–20 USD** | **好** | **IP 來自真實住宅 ISP，效果最佳** |

### 效果評估

- ✅ 住宅型代理效果好，能同時解決 `youtube-transcript-api` 和 `yt-dlp` 的封鎖問題
- ✅ 改動幅度小，約 15 行程式碼
- ⚠️ YouTube 持續加強反爬蟲機制，代理 IP 也可能被輪換封鎖，不保證長期穩定
- ⚠️ 需要定期檢查代理是否仍然有效

### 後續影響

- 引入外部付費依賴，代理服務中斷 = 字幕功能中斷
- 代理品質直接影響字幕取得成功率
- 若代理 IP 也被封，需更換代理供應商
- 需在 GitHub Secrets 管理額外的 `PROXY_URL` 環境變數

---

## 方案 2：使用 YouTube Data API captions 端點

### 原理

直接用已有的 YouTube API Key 透過官方 API 取得字幕，不走網頁爬取。

### 關鍵限制（此方案基本不可行）

| 端點 | 配額成本 | 驗證需求 | 限制 |
|------|----------|----------|------|
| `captions.list` | 50 units/次 | API Key 即可 | 只能**列出**有哪些字幕軌 |
| `captions.download` | 200 units/次 | **必須 OAuth 2.0** | **只能下載自己擁有的影片字幕** |

### 核心問題

1. **`captions.download` 需要 OAuth 2.0 且限定影片擁有者**
   - 無法用 API Key 下載別人影片的字幕
   - 此端點設計給頻道主管理自己的字幕用，第三方無法取得任意公開影片的字幕內容

2. **配額成本極高**
   - `captions.list` 要 50 units（對比 `videos.list` 僅 1 unit）
   - 假設每次 run 有 5 支爆款需要字幕：`captions.list` = 5 × 50 = 250 units
   - 若能 download（實際上不行）：5 × 200 = 1,000 units
   - 佔掉目前每次 run 上限 3,000 units 的很大比例

3. **OAuth 2.0 在 GitHub Actions 中極為繁瑣**
   - 需要 refresh token 管理、token 過期處理
   - Service account 不支援 `captions.download`
   - 維護成本高

### 結論

❌ **方案 2 不可行。** YouTube Data API 的 captions 端點是為頻道主設計的，無法用於取得第三方影片字幕。

---

## 總結比較

| | 方案 1 (Proxy) | 方案 2 (Captions API) |
|---|---|---|
| **可行性** | ✅ 可行 | ❌ 不可行 |
| **改動幅度** | 小（~15 行程式碼） | N/A |
| **費用** | $5–20 USD/月（住宅型代理） | N/A |
| **效果** | 好（住宅型代理可穩定繞過封鎖） | N/A |
| **風險** | 代理品質衰退、需維護 | N/A |

---

## 替代思路：接受現狀 + 品質門檻

若不想引入持續費用和外部依賴，可考慮在程式邏輯中加入品質門檻：

- 當 `transcript_source == "none"` 時，標註為「僅 metadata 分析」或跳過不建 Issue
- 成本為零，改動極小（在 `src/main.py` 的 Issue 建立邏輯加一個判斷即可）
- 缺點是所有字幕分析能力完全喪失，Issue 品質依賴 metadata 品質
