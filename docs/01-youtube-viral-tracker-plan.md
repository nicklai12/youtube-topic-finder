# Plan: YouTube 爆款影片自動追蹤 via GitHub Issues

## TL;DR

使用 GitHub Actions 每 6 小時定時執行 Python 腳本，透過 YouTube Data API v3 搜尋「科技/程式」和「財經/投資」領域的影片，根據「觀看門檻 + 短期成長率」雙條件篩選爆款，自動建立 GitHub Issue 紀錄。全程在 YouTube API (10,000 units/day) 和 GitHub Actions (public repo 無限) 免費額度內運行。

---

## 配額分析

### YouTube Data API v3 (免費 10,000 units/day)
| 操作 | 單位成本 | 每次執行次數 | 小計 |
|------|---------|------------|------|
| search.list (關鍵字搜尋) | 100 units | 6 次 (2 主題 × 3 關鍵字) | 600 |
| videos.list (取影片詳情) | 1 unit | ~3 次 (每次最多 50 支 ID) | 3 |
| videos.list (成長追蹤覆查) | 1 unit | ~2 次 (追蹤中的影片) | 2 |
| **每次執行合計** | | | **~605** |
| **每日合計 (4 次/天)** | | | **~2,420** |
| **佔每日額度** | | | **~24%** |

### GitHub Actions (public repo)
- Public repo：**無限分鐘數**
- Private repo：2,000 分鐘/月（每次 ~1-2 分鐘 × 4 次/天 × 30 天 = ~240 分鐘/月）
- 結論：兩者都完全足夠

### GitHub API
- 認證請求 5,000 次/小時，遠超需求

---

## Steps

### Phase 1: 專案基礎建設

1. **建立 `.gitignore`**
   - 忽略 `__pycache__/`, `.env`, `venv/` 等

2. **建立 `requirements.txt`**
   - `google-api-python-client` (YouTube API)
   - `PyGithub` (GitHub Issue 管理)

3. **建立 `config.py` — 搜尋設定與爆款條件**
   - 搜尋關鍵字配置（科技/程式、財經/投資各 3 個關鍵字組）
   - 爆款判定條件：
     - **門檻條件**：發布 48 小時內 > 50,000 觀看次數，或發布 7 天內 > 500,000 觀看次數
     - **成長條件**：6 小時內觀看數成長 > 100%（基於 `data/tracking.json` 歷史數據比較）
   - YouTube API 配額上限保護（每次執行最多消耗 units 數）

### Phase 2: 核心腳本

4. **建立 `youtube_client.py` — YouTube API 封裝**
   - `search_videos(keyword, published_after, max_results=25)` → 呼叫 search.list，回傳 video ID 列表
   - `get_video_details(video_ids)` → 呼叫 videos.list，回傳 title, channel, viewCount, likeCount, publishedAt, thumbnail, duration
   - 內建配額計算器：累計已使用 units，超過安全上限時停止

5. **建立 `tracker.py` — 成長追蹤邏輯**
   - 讀取 `data/tracking.json`（紀錄上次執行時每支影片的觀看次數）
   - 計算每支影片的成長率 = (current_views - last_views) / last_views
   - 寫回更新後的 `data/tracking.json`
   - 清理 > 14 天未更新的影片記錄（避免 JSON 無限增長）

6. **建立 `viral_detector.py` — 爆款判定**
   - `is_viral(video_detail, growth_info)` → 根據 config 的門檻與成長條件判斷
   - 回傳 `(is_viral: bool, reason: str)`，例如 "發布 12 小時已達 120K 觀看" 或 "6 小時內觀看成長 150%"

7. **建立 `issue_manager.py` — GitHub Issue 管理**
   - `find_existing_issue(video_id)` → 搜尋 repo 中是否已有此影片的 Issue（用 video_id 作為唯一識別，放在 Issue body）
   - `create_issue(video_detail, viral_reason)` → 建立新 Issue，格式：
     ```
     Title: 🔥 {影片標題}
     Labels: viral, {topic_label}
     Body:
     - 影片連結
     - 頻道名稱 + 連結
     - 觀看次數 / 按讚數 / 發布時間
     - 爆款原因
     - 縮圖
     ```
   - `update_issue_comment(issue, new_stats)` → 對已存在的 Issue 新增留言更新統計數據（可選）

8. **建立 `main.py` — 主流程**
   - 讀取環境變數 `YOUTUBE_API_KEY` 和 `GITHUB_TOKEN`
   - 遍歷所有關鍵字 → 搜尋 → 取詳情 → 判定爆款 → 查重 → 建 Issue
   - 更新 tracking.json 並 commit/push 回 repo
   - 輸出執行摘要（找到 N 支影片，新建 M 個 Issue）

### Phase 3: GitHub Actions 自動化

9. **建立 `.github/workflows/track-viral.yml`**
   - 觸發條件：`schedule: cron '0 */6 * * *'`（每 6 小時）+ `workflow_dispatch`（手動觸發測試用）
   - Steps:
     1. Checkout repo
     2. Setup Python 3.11
     3. Install dependencies
     4. Run `main.py`（環境變數注入 `YOUTUBE_API_KEY` 和 `GITHUB_TOKEN`）
     5. Commit & push `data/tracking.json` 變更
   - Secrets 需設定：`YOUTUBE_API_KEY`

10. **建立 `data/tracking.json`** — 初始空 JSON `{}`
    - 此檔案由 Actions 自動維護，紀錄影片觀看數歷史

### Phase 4: Issue 組織

11. **設定 GitHub Labels**（在 workflow 中自動建立或手動設定）
    - `viral` — 爆款影片
    - `tech` — 科技/程式類
    - `finance` — 財經/投資類
    - `growth-spike` — 成長率觸發
    - `view-threshold` — 觀看門檻觸發

---

## 專案結構

```
youtube-topic-finder/
├── .github/
│   └── workflows/
│       └── track-viral.yml
├── data/
│   └── tracking.json
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── youtube_client.py
│   ├── tracker.py
│   ├── viral_detector.py
│   ├── issue_manager.py
│   └── main.py
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Relevant Files (to create)

- `.github/workflows/track-viral.yml` — GitHub Actions 定時工作流，包含 cron、checkout、Python setup、環境變數、auto-commit
- `src/config.py` — 搜尋關鍵字定義、爆款門檻參數、配額限制常數
- `src/youtube_client.py` — YouTube Data API v3 封裝，search.list + videos.list，含配額追蹤
- `src/tracker.py` — 讀寫 `data/tracking.json`，計算成長率，清理過期記錄
- `src/viral_detector.py` — 爆款判定邏輯，結合門檻條件與成長條件
- `src/issue_manager.py` — GitHub Issue CRUD，使用 PyGithub，含去重邏輯（基於 video_id）
- `src/main.py` — 主入口，串接所有模組
- `data/tracking.json` — 影片觀看數歷史紀錄（由 Actions 自動維護）
- `requirements.txt` — google-api-python-client, PyGithub
- `.gitignore` — 標準 Python gitignore

---

## Verification

1. **手動觸發測試**：設定好 Secrets 後，在 GitHub Actions 頁面手動觸發 `workflow_dispatch`，確認：
   - Workflow 成功完成
   - 至少建立一個測試 Issue（可先降低門檻為 1,000 觀看次數來測試）
   - `data/tracking.json` 被正確更新並 commit
2. **去重驗證**：手動再觸發一次，確認不會重複建立相同影片的 Issue
3. **配額監控**：在 Google Cloud Console 的 API 儀表板確認每日使用量 < 2,500 units
4. **成長追蹤驗證**：等待兩次執行後，確認 `data/tracking.json` 中有成長率計算，且成長觸發的 Issue 有正確的 `growth-spike` label
5. **錯誤處理測試**：暫時設定無效 API key，確認 workflow 失敗但不會 crash，有明確錯誤訊息

---

## Decisions

- **語言**：Python 3.11（YouTube API 官方客戶端完善，生態成熟）
- **GitHub Issue 操作**：使用 PyGithub 而非 gh CLI，方便進行 Issue 搜尋和去重
- **追蹤資料儲存**：使用 `data/tracking.json` commit 到 repo（簡單、有版本歷史、無需外部服務）
- **auto-commit**：使用 `stefanzweifel/git-auto-commit-action` 自動 commit tracking.json 變更
- **搜尋策略**：每個主題 3 組關鍵字，每組限 25 筆結果，做去重後再查詳情
- **爆款門檻**：初始值設為 48 小時內 50K 觀看或 7 天內 500K 觀看。可在 config.py 中調整
- **Issue 去重**：在 Issue body 中嵌入 `<!-- video_id: {id} -->` HTML 註解，搜尋時用此識別
- **Repo 類型建議**：Public repo（GitHub Actions 無限分鐘）
- **排除範圍**：不含通知功能（Slack/Discord），不含影片內容摘要，不含 AI 分析

---

## Further Considerations

1. **YouTube API Key 取得**：需在 Google Cloud Console 建立專案 → 啟用 YouTube Data API v3 → 建立 API Key → 加入 GitHub repo Secrets `YOUTUBE_API_KEY`。建議加上 API Key 限制（僅允許 YouTube Data API）。
2. **關鍵字調優**：初始關鍵字可能需要迭代。建議先用廣泛詞（如 "Python tutorial", "投資理財"），觀察一週後根據 Issue 品質調整。config.py 設計為易於修改。
3. **未來擴展性**：若之後想追蹤更多主題或加入通知，架構已模組化，只需修改 config.py 加主題、或新增 notification 模組。
