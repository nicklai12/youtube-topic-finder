# Plan: 二創分析功能（AI 爆紅分析 + 摘要 + 二創角度建議）

## TL;DR

為已偵測到的爆款影片自動擷取字幕，透過 Google Gemini Flash 生成：

1. **爆紅原因分析** — 為什麼這支影片會爆？
2. **內容摘要** — 重點整理
3. **二創角度建議** — 可以從哪些切入點做二創？

分析結果直接嵌入 GitHub Issue，讓閱讀者一目了然。

---

## 配額影響評估

| 資源 | 現有消耗 | 新增消耗 | 合計 | 免費額度 | 佔比 |
|------|---------|---------|------|---------|------|
| YouTube Data API | ~2,420 units/天 | +0 | ~2,420 | 10,000 units/天 | 24% |
| Gemini Flash API | 0 | ~40 req/天 | ~40 | 1,500 req/天 | 2.7% |
| GitHub Actions | 現有 4 次/天 | +0 | 4 次/天 | 公開 repo 無限 | — |

- **YouTube API +0**：字幕擷取使用 `youtube-transcript-api`，走非官方路線，不消耗配額
- **Gemini Flash ~40 req/天**：假設每次執行偵測到 ~10 支新爆款，每天 4 次 = 40 req，僅佔免費額度 2.7%
- **新增 Secret**：`GEMINI_API_KEY`（從 [Google AI Studio](https://aistudio.google.com/) 免費取得）

---

## 新增依賴

```
youtube-transcript-api>=1.0.0    # 字幕擷取（免費、無需 API Key）
google-generativeai>=0.8.0       # Gemini Flash API 客戶端
```

---

## 檔案變動清單

| 檔案 | 動作 | 說明 |
|------|------|------|
| `src/transcript.py` | **新增** | 字幕擷取模組 |
| `src/analyzer.py` | **新增** | Gemini AI 分析模組 |
| `src/config.py` | 修改 | 新增 analyzer 相關設定 |
| `src/issue_manager.py` | 修改 | Issue body 加入分析區塊 |
| `src/main.py` | 修改 | 串接字幕 → 分析 → Issue |
| `config.yml` / `config.yml.example` | 修改 | 新增 analyzer 設定區塊 |
| `requirements.txt` | 修改 | 新增兩個套件（順便修復重複 PyYAML） |
| `.github/workflows/track-viral.yml` | 修改 | 新增 `GEMINI_API_KEY` 環境變數 |

---

## 執行計畫（6 個階段）

### Phase 1：字幕擷取模組 — `src/transcript.py`

**職責**：給定 video_id，嘗試取得字幕文本。

```python
def get_transcript(video_id: str, preferred_langs: list[str]) -> str | None
```

- 使用 `youtube-transcript-api` 套件
- 優先取得 `preferred_langs`（預設 `["zh-TW", "zh-Hant", "zh", "en"]`）
- 字幕不存在 → 回傳 `None`（靜默失敗，不影響主流程）
- 將字幕片段拼接為純文字，截斷至 `max_chars`（預設 15,000 字元，約 Gemini Flash 的安全輸入長度）

### Phase 2：AI 分析模組 — `src/analyzer.py`

**職責**：將字幕 + 影片 metadata 送入 Gemini，取得結構化分析。

```python
def analyze_video(video: dict, transcript: str | None) -> dict | None
```

**回傳格式**：
```python
{
    "viral_reason": "...",       # 爆紅原因分析
    "summary": "...",            # 內容摘要（3-5 段）
    "recreate_angles": ["...", "...", "..."],  # 二創角度建議
    "has_transcript": True/False
}
```

**設計要點**：
- 使用 `gemini-2.0-flash` 模型（免費、快速、支援長上下文）
- Prompt 以繁體中文撰寫，輸出也要求繁體中文
- 沒有字幕時仍可依 title + 頻道名 + 觀看數等 metadata 做「僅 metadata 分析」，但品質較低，會在結果中標註
- 沒有 `GEMINI_API_KEY` → 整個模組靜默跳過，回傳 `None`
- 任何 API 錯誤 → log warning + 回傳 `None`（不影響 Issue 建立）

**Prompt 結構**：
```
你是一位 YouTube 內容分析師與二創策略顧問。

以下是一支近期爆紅的 YouTube 影片資訊：
- 標題：{title}
- 頻道：{channel}
- 觀看數：{views}
- 發布時間：{published}
[如有字幕]
- 字幕內容：{transcript}

請用繁體中文分析以下三點：

## 爆紅原因分析
分析這支影片爆紅的可能原因...

## 內容摘要
整理影片的核心內容...

## 二創角度建議
提供 3-5 個具體的二創切入角度...
```

### Phase 3：`src/config.py` 修改

新增以下設定項（可透過 `config.yml` 覆蓋）：

```yaml
analyzer:
  enabled: true
  model: "gemini-2.0-flash"
  preferred_langs: ["zh-TW", "zh-Hant", "zh", "en"]
  max_transcript_chars: 15000
  prompt_template: null  # null 表示使用內建 prompt
```

對應 Python 變數：
- `ANALYZER_ENABLED: bool`
- `ANALYZER_MODEL: str`
- `ANALYZER_PREFERRED_LANGS: list[str]`
- `ANALYZER_MAX_TRANSCRIPT_CHARS: int`

### Phase 4：`src/issue_manager.py` 修改

**`create_issue()` 簽名變更**：新增 `analysis: dict | None = None` 參數

**`_build_body()` 擴展**：當 `analysis` 存在時，在原有 Issue body 後方追加：

```markdown
---

## 🤖 AI 分析

### 爆紅原因
{viral_reason}

### 內容摘要
{summary}

### 💡 二創角度建議
1. {angle_1}
2. {angle_2}
3. {angle_3}

> ℹ️ 分析由 Gemini Flash 自動生成，僅供參考
> 📝 字幕來源：{有字幕/僅 metadata}
```

### Phase 5：`src/main.py` 修改

在現有流程中插入分析步驟：

```
原流程：
  搜尋 → 取得詳情 → 判斷爆款 → 建立 Issue

新流程：
  搜尋 → 取得詳情 → 判斷爆款 → [擷取字幕 → AI 分析] → 建立 Issue（含分析）
```

**關鍵邏輯**：
- 只對「新偵測到的爆款」執行分析（已存在 Issue 的不重複分析）
- `ANALYZER_ENABLED = False` 或無 `GEMINI_API_KEY` → 跳過整個分析步驟
- 分析失敗 → 照常建立 Issue，只是沒有分析區塊

### Phase 6：設定檔與 CI 更新

#### `config.yml` / `config.yml.example`

新增 `analyzer` 區塊（含完整註解說明用途）。

#### `requirements.txt`

```
google-api-python-client==2.118.0
PyGithub==2.3.0
PyYAML==6.0.2
python-dateutil==2.9.0
youtube-transcript-api>=1.0.0
google-generativeai>=0.8.0
```

（同時修復現有的重複 `PyYAML` 問題）

#### `.github/workflows/track-viral.yml`

在 `env` 區塊新增：

```yaml
env:
  YOUTUBE_API_KEY: ${{ secrets.YOUTUBE_API_KEY }}
  GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}   # ← 新增
```

---

## 向下相容性保證

整個功能設計為「全可選」（fully optional）：

| 情境 | 行為 |
|------|------|
| 沒有 `GEMINI_API_KEY` | 分析完全跳過，Issue 照常建立（與現在一樣） |
| `analyzer.enabled: false` | 分析完全跳過 |
| 字幕不存在 | 降級為僅 metadata 分析（在 Issue 中標註） |
| Gemini API 錯誤 | log warning，Issue 照常建立但無分析區塊 |
| `youtube-transcript-api` 失敗 | 降級為僅 metadata 分析 |

---

## 使用者需要做的事

1. 到 [Google AI Studio](https://aistudio.google.com/) 取得免費 Gemini API Key
2. 在 GitHub repo Settings → Secrets → Actions 新增 `GEMINI_API_KEY`
3. （可選）在 `config.yml` 的 `analyzer` 區塊調整偏好語言或停用功能

---

## 驗證步驟

1. 本機測試（有 key）：`GEMINI_API_KEY=xxx python -m src.main` → 確認 Issue 出現 AI 分析區塊
2. 本機測試（無 key）：不設 GEMINI_API_KEY → 確認 Issue 正常建立，無分析區塊，無報錯
3. 本機測試（無字幕影片）：選一支無字幕影片 → 確認降級為 metadata 分析，Issue 標註「僅 metadata」
4. GitHub Actions 測試：push 後手動觸發 workflow → 確認 Actions log 顯示分析流程
