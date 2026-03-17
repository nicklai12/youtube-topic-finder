# YouTube 爆款影片自動追蹤器

每 6 小時自動掃描「科技/程式」與「財經/投資」領域的 YouTube 影片，偵測爆款後在 GitHub Issues 建立紀錄。全程在 YouTube Data API v3 與 GitHub Actions 的**免費額度**內運行（每日約消耗 24% API 配額）。

## 功能

- **定時執行**：GitHub Actions 每 6 小時觸發，也可手動觸發
  | UTC | 台灣時間（UTC+8） |
  |-----|-----------------|
  | 00:00 | 08:00 |
  | 06:00 | 14:00 |
  | 12:00 | 20:00 |
  | 18:00 | 02:00（隔日） |
- **雙重爆款條件**：
  - 門檻條件：發布 48 小時內 > 5 萬觀看，或 7 天內 > 50 萬觀看
  - 成長條件：6 小時內觀看數成長 > 100%
- **自動去重**：同一支影片不會重複建立 Issue
- **自動分類**：Issue 自動貼上 `viral`、`tech`/`finance`、`view-threshold`/`growth-spike` 標籤
- **自動關閉**：觀看數連續多次檢查無明顯成長（預設連續 3 次、即 18 小時）時，自動關閉 Issue 並留言說明
- **AI 分析（可選）**：自動擷取影片字幕，透過 Groq Kimi K2 生成爆紅原因分析、內容摘要、二創角度建議，嵌入 Issue。未設定 API Key 時自動跳過，不影響原有功能- **Whisper 語音轉文字（自動 fallback）**：當 YouTube 字幕無法取得時（IP 封鎖、影片無字幕），自動用 yt-dlp 下載音訊 + Groq Whisper API 語音轉文字，確保 AI 分析取得實際影片內容。內建每日用量追蹤與額度保護- **歷史追蹤**：`data/tracking.json` 記錄每支影片的觀看數歷史，由 Actions 自動 commit 更新

## 快速開始

### 1. 取得 YouTube Data API Key

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 建立新專案（或選擇現有專案）
3. 啟用 **YouTube Data API v3**
4. 建立 **API 金鑰**（建議限制為僅允許 YouTube Data API）

### 2. 設定 GitHub Secrets

在 repo 的 **Settings → Secrets and variables → Actions** 中新增：

| Secret 名稱 | 說明 |
|-------------|------|
| `YOUTUBE_API_KEY` | 上一步取得的 YouTube API 金鑰 |
| `GROQ_API_KEY` | （可選）Groq API 金鑰，用於 AI 分析功能。從 [Groq Console](https://console.groq.com/) 免費取得 |

> `GITHUB_TOKEN` 由 GitHub Actions 自動提供，無需手動設定。
> 未設定 `GROQ_API_KEY` 時，AI 分析功能會自動跳過，Issue 照常建立。

### 3. 確認 Repo 為 Public（建議）

Public repo 的 GitHub Actions 有無限免費分鐘數。  
Private repo 也支援，但每月免費分鐘數為 2,000 分鐘（本專案每月約用 240 分鐘）。

### 4. 手動觸發測試

推送程式碼後，前往 **Actions → Track Viral YouTube Videos → Run workflow**，確認：
- Workflow 成功完成
- Issues 頁面出現爆款影片紀錄
- `data/tracking.json` 有自動 commit

## 自訂設定

複製範本檔後編輯即可自訂所有參數：

```bash
cp config.yml.example config.yml
```

`config.yml` 已加入 `.gitignore`，不會被 commit（保護個人化設定）。  
若刪除 `config.yml`，程式會自動使用 `src/config.py` 內的預設值繼續運行。

```yaml
# config.yml — 可自訂項目

topics:
  tech:
    label: tech
    keywords:
      - Python tutorial 2025
      - AI programming
      - software engineering
  finance:
    label: finance
    keywords:
      - 投資理財 2025
      - 股票分析
      - ETF 被動投資

viral:
  threshold_fast:     # 發布 48 小時內 > 5 萬觀看
    hours: 48
    views: 50000
  threshold_slow:     # 發布 7 天內 > 50 萬觀看
    days: 7
    views: 500000
  growth_rate: 1.0    # 成長率門檻（1.0 = 100%）

search:
  published_within_days: 7
  max_results: 25

quota:
  max_units_per_run: 3000

tracking:
  expiry_days: 14

auto_close:
  enabled: true        # 觀看數不再成長時自動關閉 Issue
  growth_below: 0.05   # 低於 5% 視為無成長
  stale_count: 3       # 連續 3 次（18 小時）無成長後自動關閉

analyzer:
  enabled: true                                   # 啟用 AI 分析（需設定 GROQ_API_KEY）
  model: "moonshotai/kimi-k2-instruct-0905"          # 使用的 Groq 模型
  preferred_langs: ["zh-TW", "zh-Hant", "zh", "en"] # 字幕語言偏好
  max_transcript_chars: 15000                      # 送入 LLM 的字幕最大字元數
  whisper_enabled: true                            # Whisper 語音轉文字 fallback
  whisper_model: "whisper-large-v3-turbo"           # Whisper 模型
  max_audio_duration_minutes: 30                   # 超過此時長的影片跳過 Whisper
  whisper_daily_limit_seconds: 6000                # 每日 Whisper 用量上限（秒）
```

完整參數說明請參考 [config.yml.example](config.yml.example)。

## 專案結構

```
youtube-topic-finder/
├── .github/workflows/track-viral.yml  # 定時排程 + 手動觸發
├── config.yml.example                 # 設定檔範本（複製為 config.yml 使用）
├── data/tracking.json                 # 觀看數歷史（自動維護）
├── docs/
│   ├── 01-youtube-viral-tracker-plan.md
│   ├── 02-ai-analyzer-plan.md
│   ├── 03-migrate-gemini-to-groq-plan.md
│   ├── 04-groq-model-comparison.md
│   └── 05-whisper-fallback-plan.md
├── src/
│   ├── config.py          # 載入 config.yml + 預設值
│   ├── youtube_client.py  # YouTube API 封裝 + 配額計算器
│   ├── tracker.py         # tracking.json 讀寫 + 成長率計算
│   ├── viral_detector.py  # 爆款判定邏輯
│   ├── issue_manager.py   # GitHub Issue 建立 + 去重 + 自動關閉
│   ├── transcript.py      # YouTube 字幕擷取 + Whisper 語音轉文字 fallback
│   ├── analyzer.py        # Groq Kimi K2 AI 分析
│   └── main.py            # 主入口
├── requirements.txt
└── README.md
```

## 配額使用說明

| 資源 | 免費額度 | 預估每日用量 |
|------|---------|------------|
| YouTube Data API v3 | 10,000 units/天 | ~2,420 units（24%） |
| Groq LLM API | 1,000 req/天、1,000 RPD、300K TPD | ~40 req（4%） |
| Groq Whisper API | ~7,200 秒/天 | ~400 分鐘（預設上限 100 分鐘/天）|
| GitHub Actions（Public） | 無限分鐘 | ~8 分鐘 |
| GitHub API | 5,000 req/小時 | <200 req |
