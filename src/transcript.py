"""YouTube 字幕擷取模組：優先使用 youtube-transcript-api，IP 封鎖時 fallback 到 yt-dlp + Groq Whisper。"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

_DEFAULT_PREFERRED_LANGS = ["zh-TW", "zh-Hant", "zh", "en"]

# Groq Whisper 只接受 ISO 639-1 語言碼，將常見變體對映
_LANG_TO_ISO1: dict[str, str] = {
    "zh-TW": "zh", "zh-Hant": "zh", "zh-Hans": "zh", "zh": "zh",
    "en": "en", "ja": "ja", "ko": "ko",
}

# Groq Whisper 檔案上限 25 MB，留 1 MB buffer
_WHISPER_MAX_FILE_BYTES = 24 * 1024 * 1024


@dataclass
class TranscriptResult:
    """字幕擷取結果，記錄文字內容、來源與 Whisper 音訊時長。"""
    text: str | None
    source: Literal["youtube", "whisper", "none"]
    audio_duration_sec: float | None = None


def get_transcript(
    video_id: str,
    preferred_langs: list[str] | None = None,
    max_chars: int = 15_000,
    whisper_enabled: bool = True,
    whisper_model: str = "whisper-large-v3-turbo",
    max_audio_duration_minutes: int = 30,
    groq_api_key: str | None = None,
) -> TranscriptResult:
    """
    擷取指定 YouTube 影片的字幕文字。

    優先使用 youtube-transcript-api（零成本）；
    若失敗且 whisper_enabled=True，fallback 到 yt-dlp 下載音訊 + Groq Whisper 語音轉文字。

    Args:
        video_id: YouTube 影片 ID
        preferred_langs: 語言偏好順序，依序嘗試。預設 ["zh-TW", "zh-Hant", "zh", "en"]
        max_chars: 回傳文字最大字元數
        whisper_enabled: 是否允許 Whisper fallback
        whisper_model: Groq Whisper 模型名稱
        max_audio_duration_minutes: 超過此時長（分鐘）的影片跳過 Whisper 下載
        groq_api_key: Groq API Key；None 時從環境變數 GROQ_API_KEY 取得

    Returns:
        TranscriptResult，source 為 "youtube" / "whisper" / "none"
    """
    langs = preferred_langs or _DEFAULT_PREFERRED_LANGS
    _none = TranscriptResult(text=None, source="none")

    # ── 優先：youtube-transcript-api ─────────────────────────────────────────
    text = _fetch_youtube_transcript(video_id, langs, max_chars)
    if text is not None:
        return TranscriptResult(text=text, source="youtube")

    # ── Fallback：yt-dlp + Groq Whisper ──────────────────────────────────────
    if not whisper_enabled:
        return _none

    key = groq_api_key or os.environ.get("GROQ_API_KEY", "")
    if not key:
        logger.debug("GROQ_API_KEY 未設定，跳過 Whisper fallback")
        return _none

    audio_path: str | None = None
    tmpdir: str | None = None
    try:
        audio_path, duration_sec, tmpdir = _download_audio(video_id, max_audio_duration_minutes)
        if audio_path is None:
            return _none

        whisper_lang = next(
            (_LANG_TO_ISO1[lang] for lang in langs if lang in _LANG_TO_ISO1), None
        )
        text = _transcribe_audio(audio_path, key, whisper_model, whisper_lang, max_chars)
        if text is None:
            return _none

        logger.info(
            "影片 %s Whisper 轉錄成功，%d 字元（%.0f 秒）",
            video_id, len(text), duration_sec or 0,
        )
        return TranscriptResult(text=text, source="whisper", audio_duration_sec=duration_sec)
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ── 內部函式 ──────────────────────────────────────────────────────────────────

def _fetch_youtube_transcript(video_id: str, langs: list[str], max_chars: int) -> str | None:
    """嘗試用 youtube-transcript-api 取得字幕；失敗回傳 None。"""
    try:
        from youtube_transcript_api import (
            NoTranscriptFound,
            TranscriptsDisabled,
            YouTubeTranscriptApi,
        )
    except ImportError:
        logger.warning("youtube-transcript-api 未安裝，無法擷取字幕（pip install youtube-transcript-api）")
        return None

    try:
        ytt_api = YouTubeTranscriptApi()
        fetched = ytt_api.fetch(video_id, languages=langs)
        text = " ".join(snippet.text for snippet in fetched).strip()
        if not text:
            return None
        if len(text) > max_chars:
            text = text[:max_chars] + "…（字幕已截斷）"
        logger.debug("影片 %s YouTube 字幕擷取成功，%d 字元", video_id, len(text))
        return text
    except TranscriptsDisabled:
        logger.debug("影片 %s 已停用字幕", video_id)
        return None
    except NoTranscriptFound:
        logger.debug("影片 %s 找不到字幕", video_id)
        return None
    except Exception as exc:
        logger.warning("影片 %s 字幕擷取失敗: %s", video_id, exc)
        return None


def _download_audio(
    video_id: str,
    max_duration_minutes: int,
) -> tuple[str | None, float | None, str | None]:
    """
    使用 yt-dlp 下載影片音訊到暫存目錄。

    Returns:
        (audio_path, duration_sec, tmpdir)；若跳過或失敗回傳 (None, None, None)
    """
    try:
        import yt_dlp
    except ImportError:
        logger.warning("yt-dlp 未安裝，無法執行 Whisper fallback（pip install yt-dlp）")
        return None, None, None

    url = f"https://www.youtube.com/watch?v={video_id}"
    max_duration_sec = max_duration_minutes * 60
    tmpdir = tempfile.mkdtemp(prefix="yt_whisper_")

    # Step 1：取 info 確認時長（不下載），避免下載過長影片
    info_opts: dict = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get("duration") if info else None
    except Exception as exc:
        logger.warning("影片 %s 取得時長失敗: %s", video_id, exc)
        shutil.rmtree(tmpdir, ignore_errors=True)
        return None, None, None

    if duration and duration > max_duration_sec:
        logger.info(
            "影片 %s 時長 %.0f 分鐘，超過上限 %d 分鐘，跳過 Whisper",
            video_id, duration / 60, max_duration_minutes,
        )
        shutil.rmtree(tmpdir, ignore_errors=True)
        return None, None, None

    # Step 2：下載音訊
    dl_opts: dict = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": os.path.join(tmpdir, "audio.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            ydl.download([url])
    except Exception as exc:
        logger.warning("影片 %s 音訊下載失敗: %s", video_id, exc)
        shutil.rmtree(tmpdir, ignore_errors=True)
        return None, None, None

    # 找出實際下載的檔案
    files = [f for f in os.listdir(tmpdir) if f.startswith("audio.")]
    if not files:
        logger.warning("影片 %s 找不到下載的音訊檔", video_id)
        shutil.rmtree(tmpdir, ignore_errors=True)
        return None, None, None

    audio_path = os.path.join(tmpdir, files[0])
    file_size = os.path.getsize(audio_path)
    if file_size > _WHISPER_MAX_FILE_BYTES:
        logger.warning(
            "影片 %s 音訊檔案 %.1f MB 超過 Groq 上限 24 MB，跳過 Whisper",
            video_id, file_size / 1024 / 1024,
        )
        shutil.rmtree(tmpdir, ignore_errors=True)
        return None, None, None

    logger.debug(
        "影片 %s 音訊下載成功（%.1f MB）", video_id, file_size / 1024 / 1024
    )
    return audio_path, float(duration) if duration else None, tmpdir


def _transcribe_audio(
    audio_path: str,
    api_key: str,
    model: str,
    language: str | None,
    max_chars: int,
) -> str | None:
    """使用 Groq Whisper API 將音訊轉為文字。"""
    try:
        from groq import Groq
    except ImportError:
        logger.warning("groq 未安裝，無法執行 Whisper 語音轉文字")
        return None

    client = Groq(api_key=api_key)
    try:
        with open(audio_path, "rb") as f:
            kwargs: dict = {
                "model": model,
                "file": f,
                "response_format": "text",
            }
            if language:
                kwargs["language"] = language
            result = client.audio.transcriptions.create(**kwargs)

        # response_format="text" 直接回傳字串；防禦性處理其他型別
        text = result if isinstance(result, str) else getattr(result, "text", str(result))
        text = text.strip()
        if not text:
            return None
        if len(text) > max_chars:
            text = text[:max_chars] + "…（字幕已截斷）"
        return text
    except Exception as exc:
        logger.warning("Whisper 語音轉文字失敗: %s", exc)
        return None
