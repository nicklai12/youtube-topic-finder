# 03 — 從 Gemini 遷移至 Groq 免費 LLM API

## 背景

Gemini API 免費方案配額已歸零，需遷移至其他免費 LLM API。經研究 Groq 與 Cerebras 免費方案後，選擇 **Groq API + `llama-3.3-70b-versatile`**。

---

## 專案 AI 使用摘要

- **用途**：分析爆款 YouTube 影片（爆紅原因、摘要、二創角度）
- **當前模型**：`gemini-2.0-flash`
- **每次請求輸入**：prompt (~500 chars) + 字幕 (最多 15,000 chars) ≈ ~4,000–5,000 tokens
- **輸出**：JSON 格式，`max_output_tokens=1024`
- **日請求量**：~40 次（4 次執行 × ~10 影片）
- **關鍵需求**：繁體中文輸出、JSON 格式輸出

---

## Groq vs Cerebras 比較

| 項目 | Groq 免費方案 | Cerebras 免費方案 |
|------|-------------|-----------------|
| **可用模型** | Llama 3.3 70B, Llama 3.1 8B, Gemma 2 9B, Mixtral 等 | Llama 3.3 70B, Llama 3.1 8B |
| **每日請求上限** | 14,400 req/day (70B 模型) | ~1,000 req/day（較嚴格） |
| **每分鐘請求** | 30 req/min | 30 req/min |
| **Token 限制** | ~6,000 output tokens/min | ~60,000 tokens/min |
| **JSON Mode** | ✅ `response_format={"type": "json_object"}` | ✅ OpenAI 相容 |
| **API 相容性** | OpenAI SDK 相容 | OpenAI SDK 相容 |
| **繁中品質 (70B)** | ✅ 良好 | ✅ 良好（同模型） |
| **生態成熟度** | 高，文件完善 | 中等 |
| **Python SDK** | `groq` 套件 | `cerebras-cloud-sdk` |

---

## 決策：Groq API + `llama-3.3-70b-versatile`

### 理由

1. **配額充裕** — 14,400 req/day 遠超本專案 ~40 req/day 需求（使用率 <0.3%）
2. **模型品質** — Llama 3.3 70B 繁中輸出品質在開源模型中屬上乘，足以勝任 150–200 字的分析任務
3. **JSON 模式原生支援** — 可確保回傳格式正確，減少解析失敗
4. **OpenAI 相容 API** — 遷移簡單，且未來可輕鬆切換其他供應商
5. **成熟穩定** — 文件齊全、社群大、故障少

### 未選擇的方案

- **Cerebras** — 每日配額僅 ~1,000 req，不如 Groq 寬裕
- **8B 小模型** — 繁中輸出品質明顯下降，不適合面向用戶的分析報告

---

## 實作步驟

### Phase 1: 依賴與配置更新

1. **`requirements.txt`** — 移除 `google-generativeai>=0.8.0`，新增 `groq>=0.9.0`
2. **`config.yml` / `config.yml.example`** — `model` 欄位改為 `llama-3.3-70b-versatile`
3. **`src/config.py`** — 環境變數從 `GEMINI_API_KEY` 改為 `GROQ_API_KEY`，預設模型更新

### Phase 2: 核心 Analyzer 遷移

4. **重寫 `src/analyzer.py`** 的 `analyze_video()` 函數：
   - `import google.generativeai as genai` → `from groq import Groq`
   - 初始化改為 `client = Groq(api_key=key)`
   - API 呼叫改為 `client.chat.completions.create(model, messages, response_format, temperature, max_tokens)`
   - Prompt 從單一字串改為 `messages` 格式（system + user）
   - 啟用 `response_format={"type": "json_object"}` 確保 JSON 輸出
   - Retry 邏輯保持相同（指數退避），錯誤碼判斷調整為 Groq 格式
5. **Prompt 結構調整** — system message 定義角色，user message 提供影片資訊；分析邏輯內容不變

### Phase 3: Issue 與文件更新

6. **`src/issue_manager.py`** — AI 分析區塊 footer 從「Gemini Flash 自動生成」改為「Llama 3.3 70B (Groq) 自動生成」
7. **`README.md`** — 環境變數說明、模型說明
8. **`docs/02-ai-analyzer-plan.md`** — 反映新的 API 選擇

---

## 影響範圍

| 檔案 | 變更 |
|------|------|
| `src/analyzer.py` | 重寫 API 呼叫邏輯（import、client 初始化、messages 格式、retry） |
| `src/config.py` | 環境變數 `GEMINI_API_KEY` → `GROQ_API_KEY`，預設模型名稱 |
| `config.yml` / `config.yml.example` | `model` 值更新 |
| `requirements.txt` | 套件替換 |
| `src/issue_manager.py` | footer 文字小修 |
| `README.md` | 文件更新 |

---

## 驗證計畫

1. 設定 `GROQ_API_KEY` 環境變數後，以簡單請求驗證 API 連線
2. 執行完整流程 `python -m src.main`，確認爆款影片 AI 分析正常產生
3. 檢查 GitHub Issue 中 AI 分析區塊格式正確、繁中輸出品質可接受
4. 故意不設 `GROQ_API_KEY`，確認優雅降級（Issue 照常建立但無分析區塊）

---

## 後續考量

- **Fallback 機制** — 目前不需要備援供應商，Groq 配額足夠。若未來需要可加入 Cerebras 作為 fallback。
- **模型更新** — Groq 會持續上新模型（如 Llama 4），`config.yml` 中的 `model` 欄位已支援動態切換。
- **Temperature 調整** — Llama 3.3 與 Gemini 在相同 temperature 下行為可能略有差異，若輸出風格不理想可微調（建議先用 0.4 測試）。
