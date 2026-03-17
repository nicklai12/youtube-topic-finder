# 05 — yt-dlp + Groq Whisper Fallback 語音轉文字

## TL;DR

當 `youtube-transcript-api` 無法取得字幕時（IP 封鎖、無字幕），改用 `yt-dlp` 下載音訊 + Groq Whisper API 語音轉文字，作為 fallback 確保 AI 分析能取得影片實際內容，大幅提升摘要品質。

## 背景

- GitHub Actions 雲端 IP 被 YouTube 封鎖，`youtube-transcript-api` 100% 失敗
- 並非所有影片都有字幕（自動或手動）
- 目前無字幕時 AI 只能依靠 metadata（標題、頻道、觀看數），摘要品質低
- 專案已有 `GROQ_API_KEY`，Groq 提供免費 Whisper large-v3 語音轉文字 API

## Steps

### Phase 1: transcript.py — 新增 Whisper fallback

1. **新增 `_download_audio()` 內部函式**
   - 使用 `yt-dlp` 下載僅音訊（`-f ba[ext=m4a]` 或 `bestaudio`）
   - 儲存到 `tempfile.NamedTemporaryFile`，避免磁碟殘留
   - 設定下載限制：最長 30 分鐘影片（超過跳過，避免時間過長）
   - 回傳音訊檔案路徑或 None

2. **新增 `_transcribe_audio()` 內部函式**
   - 呼叫 Groq Whisper API (`client.audio.transcriptions.create`)
   - 模型：`whisper-large-v3-turbo`（速度快、免費額度高）
   - 設定 `language` 參數依現有 `preferred_langs` 配置
   - 設定 `response_format="text"` 直接取得純文字
   - Groq Whisper 限制：檔案最大 25MB，需確保音訊檔不超過
   - 同樣截斷至 `max_chars`（15,000 字元）
   - 回傳文字或 None

3. **修改 `get_transcript()` 主函式 — 加入 fallback 邏輯**
   - 保持現有 `youtube-transcript-api` 為首選（零成本、速度快）
   - 若失敗，呼叫 `_download_audio()` → `_transcribe_audio()`
   - 新增參數 `whisper_enabled: bool = True` 控制是否啟用 fallback
   - 新增參數 `groq_api_key: str | None = None`
   - 確保 fallback 失敗時仍回傳 None（保持現有容錯行為）
   - 在 finally 中清理暫存音訊檔

### Phase 2: config.py — 新增 Whisper 相關設定

4. **在 `_analyzer` 區塊新增設定項**（*parallel with step 1-3*）
   - `whisper_enabled`: bool，預設 True
   - `whisper_model`: str，預設 `"whisper-large-v3-turbo"`
   - `max_audio_duration_minutes`: int，預設 30（超過不下載）
   - 從 config.yml `analyzer` 區塊讀取

### Phase 3: main.py — 傳遞參數

5. **修改 `get_transcript()` 呼叫**（*depends on 3, 4*）
   - 傳入 `whisper_enabled=config.WHISPER_ENABLED`
   - 傳入 `groq_api_key=os.environ.get("GROQ_API_KEY")`

### Phase 4: 依賴與部署

6. **requirements.txt** — 新增 `yt-dlp` 依賴（*parallel with step 1-5*）

7. **GitHub Actions workflow** — 安裝 `ffmpeg`（*parallel with step 6*）
   - `yt-dlp` 轉檔需要 `ffmpeg`
   - 在 workflow 中加入 `apt-get install -y ffmpeg` 或使用 `FedericoCarboni/setup-ffmpeg` action

8. **config.yml + config.yml.example** — 新增 whisper 設定項（*parallel with step 6*）

### Phase 5: Whisper 用量追蹤

9. **修改 `get_transcript()` 回傳值**（*depends on 1-3*）
   - 原本回傳 `str | None`，改為回傳 `TranscriptResult` dataclass：
     - `text: str | None` — 字幕文字
     - `source: Literal["youtube", "whisper", "none"]` — 字幕來源
     - `audio_duration_sec: float | None` — Whisper 處理的音訊秒數（僅 whisper 來源有值）
   - 需同步修改 main.py 和 analyzer.py 中使用 transcript 的地方

10. **main.py 新增用量統計**（*depends on 9*）
    - 新增計數器：`whisper_total_seconds = 0.0`、`whisper_count = 0`、`youtube_transcript_count = 0`
    - 每次 Whisper fallback 成功後累加 `audio_duration_sec`
    - 每次執行前檢查剩餘額度：`whisper_daily_limit_sec`（config）- 本日累計
    - 超過額度時自動跳過 Whisper，降級為 metadata-only（不中斷整個流程）

11. **用量持久化到 tracking.json**（*depends on 10*）
    - 在 tracking.json 頂層新增 `_whisper_usage` 欄位（底線前綴，與 video_id 區隔）：
      ```json
      "_whisper_usage": {
        "2026-03-17": { "total_seconds": 580.5, "count": 8 },
        "2026-03-16": { "total_seconds": 420.0, "count": 6 }
      }
      ```
    - tracker.py 新增 `get_whisper_usage_today()` 和 `update_whisper_usage()` 函式
    - `purge_expired()` 同時清理超過 7 天的 whisper 用量記錄

12. **config.py 新增用量限制設定**（*parallel with 9-11*）
    - `whisper_daily_limit_seconds`: int，預設 6000（100 分鐘，留 20 分鐘 buffer）
    - 從 config.yml `analyzer.whisper_daily_limit_seconds` 讀取

### Phase 6: 日誌與可觀測性

13. **日誌改善**（*depends on 9-11*）
    - analyzer.py 的 `字幕：無` 改為區分三態：`字幕（YouTube）`、`字幕（Whisper）`、`無字幕`
    - transcript.py 記錄 fallback 使用情況和耗時
    - 執行摘要新增 Whisper 統計：`Whisper：3 支（共 28 分鐘）｜今日累計 85/100 分鐘`

## Relevant files

| 檔案 | 修改內容 |
|------|---------|
| `src/transcript.py` | 新增 `_download_audio()`、`_transcribe_audio()`、`TranscriptResult` dataclass，修改 `get_transcript()` 加 fallback + 回傳用量資訊 |
| `src/config.py` | 新增 `WHISPER_ENABLED`、`WHISPER_MODEL`、`MAX_AUDIO_DURATION_MINUTES`、`WHISPER_DAILY_LIMIT_SECONDS` 設定 |
| `src/main.py` | 修改 `get_transcript()` 呼叫，新增 Whisper 用量統計 + 額度檢查，更新執行摘要 |
| `src/tracker.py` | 新增 `get_whisper_usage_today()`、`update_whisper_usage()`，修改 `purge_expired()` 清理舊用量 |
| `src/analyzer.py` | 修改 `has_transcript` 為三態標記（youtube / whisper / none） |
| `data/tracking.json` | 新增 `_whisper_usage` 欄位 |
| `requirements.txt` | 新增 `yt-dlp` |
| `.github/workflows/track-viral.yml` | 安裝 ffmpeg |
| `config.yml` + `config.yml.example` | 新增 whisper 設定 |

## Verification

1. 本地測試：`GROQ_API_KEY=xxx python -m src.main`，確認 Whisper fallback 有觸發且回傳文字
2. 單元測試：mock yt-dlp 和 Groq API，驗證 fallback 流程（字幕成功→不觸發 whisper、字幕失敗→觸發 whisper、兩者都失敗→回傳 None）
3. 確認暫存檔清理：fallback 執行後 /tmp 無殘留音訊檔
4. 確認超時保護：影片超過 30 分鐘時跳過下載
5. 確認音訊檔超過 25MB 時的處理（Groq API 限制）
6. 用量追蹤驗證：確認 tracking.json 的 `_whisper_usage` 正確記錄每日用量
7. 額度保護驗證：累計秒數超過 `whisper_daily_limit_seconds` 後，後續影片自動跳過 Whisper
8. 日誌驗證：執行摘要正確顯示 Whisper 統計（次數、秒數、今日累計/上限）
9. GitHub Actions 端對端：push 後確認 workflow 能正常安裝 ffmpeg + yt-dlp 並執行

## Decisions

| 決策 | 選擇 | 原因 |
|------|------|------|
| Whisper 模型 | `whisper-large-v3-turbo` | 比 v3 快 2x，品質接近，適合批次處理 |
| 音訊格式 | m4a | 體積小、Groq 原生支援，不轉 mp3 減少 ffmpeg 依賴 |
| 影片時長上限 | 30 分鐘 | 避免長影片佔用過多時間和空間 |
| 每日額度 | 6000 秒（100 分鐘） | Groq 免費約 7200 秒/日，留 20 分鐘 buffer |
| Scope 排除 | 不做 proxy、音訊快取、並行下載 | 保持簡單，聚焦核心 fallback 功能 |
| 容錯邏輯 | Whisper 失敗不中斷流程 | 降級為 metadata-only，維持現有穩定性 |

## Further Considerations

1. **yt-dlp 在 GitHub Actions 的 IP 限制**：yt-dlp 下載音訊也可能被 YouTube 限速/封鎖（與字幕 API 相同原因）。若發現被封鎖，可考慮加入 `--extractor-args "youtube:player_client=ios"` 等繞過策略。這點需要實測確認。
