# YouTube 爆款影片自動追蹤器

每 6 小時自動掃描「科技/程式」與「財經/投資」領域的 YouTube 影片，偵測爆款後在 GitHub Issues 建立紀錄。全程在 YouTube Data API v3 與 GitHub Actions 的**免費額度**內運行（每日約消耗 24% API 配額）。

## 功能

- **定時執行**：GitHub Actions 每 6 小時觸發（UTC 0/6/12/18 點），也可手動觸發
- **雙重爆款條件**：
  - 門檻條件：發布 48 小時內 > 5 萬觀看，或 7 天內 > 50 萬觀看
  - 成長條件：6 小時內觀看數成長 > 100%
- **自動去重**：同一支影片不會重複建立 Issue
- **自動分類**：Issue 自動貼上 `viral`、`tech`/`finance`、`view-threshold`/`growth-spike` 標籤
- **歷史追蹤**：`data/tracking.json` 記錄每支影片的觀看數歷史，由 Actions 自動 commit 更新

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

> `GITHUB_TOKEN` 由 GitHub Actions 自動提供，無需手動設定。

### 3. 確認 Repo 為 Public（建議）

Public repo 的 GitHub Actions 有無限免費分鐘數。  
Private repo 也支援，但每月免費分鐘數為 2,000 分鐘（本專案每月約用 240 分鐘）。

### 4. 手動觸發測試

推送程式碼後，前往 **Actions → Track Viral YouTube Videos → Run workflow**，確認：
- Workflow 成功完成
- Issues 頁面出現爆款影片紀錄
- `data/tracking.json` 有自動 commit

## 自訂設定

編輯 [src/config.py](src/config.py) 可調整：

```python
# 搜尋主題與關鍵字
TOPICS = {
    "tech": { "keywords": ["Python tutorial 2025", ...] },
    "finance": { "keywords": ["投資理財 2025", ...] },
}

# 爆款門檻（可降低以測試）
THRESHOLD_FAST = {"hours": 48, "views": 50_000}
THRESHOLD_SLOW = {"days": 7, "views": 500_000}

# 成長率門檻（1.0 = 100%）
GROWTH_RATE_THRESHOLD = 1.0
```

## 專案結構

```
youtube-topic-finder/
├── .github/workflows/track-viral.yml  # 定時排程 + 手動觸發
├── data/tracking.json                 # 觀看數歷史（自動維護）
├── docs/
│   └── 01-youtube-viral-tracker-plan.md
├── src/
│   ├── config.py          # 搜尋主題、爆款門檻、配額上限
│   ├── youtube_client.py  # YouTube API 封裝 + 配額計算器
│   ├── tracker.py         # tracking.json 讀寫 + 成長率計算
│   ├── viral_detector.py  # 爆款判定邏輯
│   ├── issue_manager.py   # GitHub Issue 建立 + 去重
│   └── main.py            # 主入口
├── requirements.txt
└── README.md
```

## 配額使用說明

| 資源 | 免費額度 | 預估每日用量 |
|------|---------|------------|
| YouTube Data API v3 | 10,000 units/天 | ~2,420 units（24%） |
| GitHub Actions（Public） | 無限分鐘 | ~8 分鐘 |
| GitHub API | 5,000 req/小時 | <200 req |
