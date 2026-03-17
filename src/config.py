"""從專案根目錄的 config.yml 載入設定；找不到檔案時使用預設值。"""

from __future__ import annotations

import os

import yaml

# ── 載入 config.yml ───────────────────────────────────────────────────────────
_CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "config.yml")
)


def _load_yaml() -> dict:
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


_cfg = _load_yaml()

# ── 預設值 ────────────────────────────────────────────────────────────────────
_DEFAULT_TOPICS = {
    "tech": {
        "label": "tech",
        "keywords": [
            "Python tutorial 2025",
            "AI programming",
            "software engineering",
        ],
    },
    "finance": {
        "label": "finance",
        "keywords": [
            "投資理財 2025",
            "股票分析",
            "ETF 被動投資",
        ],
    },
}

# ── 搜尋主題與關鍵字（從 config.yml 的 topics 區塊載入）────────────────────────
TOPICS: dict = _cfg.get("topics", _DEFAULT_TOPICS)

# ── 搜尋參數 ──────────────────────────────────────────────────────────────────
_search = _cfg.get("search", {})
SEARCH_PUBLISHED_WITHIN_DAYS: int = _search.get("published_within_days", 7)
SEARCH_MAX_RESULTS: int = _search.get("max_results", 25)

# ── 爆款判定條件 ──────────────────────────────────────────────────────────────
_viral = _cfg.get("viral", {})
THRESHOLD_FAST: dict = _viral.get("threshold_fast", {"hours": 48, "views": 50_000})
THRESHOLD_SLOW: dict = _viral.get("threshold_slow", {"days": 7, "views": 500_000})
GROWTH_RATE_THRESHOLD: float = _viral.get("growth_rate", 1.0)

# ── 配額保護 ──────────────────────────────────────────────────────────────────
MAX_UNITS_PER_RUN: int = _cfg.get("quota", {}).get("max_units_per_run", 3_000)

# ── 追蹤資料清理 ──────────────────────────────────────────────────────────────
TRACKING_EXPIRY_DAYS: int = _cfg.get("tracking", {}).get("expiry_days", 14)

# ── 自動關閉 Issue ─────────────────────────────────────────────────────────
_auto_close = _cfg.get("auto_close", {})
# 當成長率低於此值時，計為一次「無成長」
AUTO_CLOSE_GROWTH_BELOW: float = _auto_close.get("growth_below", 0.05)
# 連續幾次「無成長」後自動關閉 Issue
AUTO_CLOSE_STALE_COUNT: int = _auto_close.get("stale_count", 3)
# 是否啟用自動關閉
AUTO_CLOSE_ENABLED: bool = _auto_close.get("enabled", True)

# ── AI 分析（Groq Llama）─────────────────────────────────────────────────────
_analyzer = _cfg.get("analyzer", {})
# 是否啟用 AI 分析（需設定 GROQ_API_KEY 環境變數）
ANALYZER_ENABLED: bool = _analyzer.get("enabled", True)
# 使用的 Groq 模型
ANALYZER_MODEL: str = _analyzer.get("model", "moonshotai/kimi-k2-instruct-0905")
# 字幕語言偏好順序
ANALYZER_PREFERRED_LANGS: list[str] = _analyzer.get(
    "preferred_langs", ["zh-TW", "zh-Hant", "zh", "en"]
)
# 送入 LLM 的字幕最大字元數
ANALYZER_MAX_TRANSCRIPT_CHARS: int = _analyzer.get("max_transcript_chars", 15_000)

# Whisper fallback 設定
WHISPER_ENABLED: bool = _analyzer.get("whisper_enabled", True)
WHISPER_MODEL: str = _analyzer.get("whisper_model", "whisper-large-v3-turbo")
MAX_AUDIO_DURATION_MINUTES: int = _analyzer.get("max_audio_duration_minutes", 30)
# Groq Whisper 每日可用約 7200 秒，預留 buffer 設為 6000 秒（100 分鐘）
WHISPER_DAILY_LIMIT_SECONDS: int = _analyzer.get("whisper_daily_limit_seconds", 6000)
