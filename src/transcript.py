"""YouTube 字幕擷取模組：使用 youtube-transcript-api，不消耗 YouTube Data API 配額。"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_DEFAULT_PREFERRED_LANGS = ["zh-TW", "zh-Hant", "zh", "en"]


def get_transcript(
    video_id: str,
    preferred_langs: list[str] | None = None,
    max_chars: int = 15_000,
) -> str | None:
    """
    擷取指定 YouTube 影片的字幕文字。

    Args:
        video_id: YouTube 影片 ID（如 "dQw4w9WgXcQ"）
        preferred_langs: 語言偏好順序，依序嘗試。預設 ["zh-TW", "zh-Hant", "zh", "en"]
        max_chars: 回傳文字最大字元數（截斷超出部分，避免超過 LLM 輸入限制）

    Returns:
        字幕純文字字串；若無字幕或發生錯誤則回傳 None
    """
    try:
        from youtube_transcript_api import (
            NoTranscriptFound,
            TranscriptsDisabled,
            YouTubeTranscriptApi,
        )
    except ImportError:
        logger.warning("youtube-transcript-api 未安裝，無法擷取字幕（pip install youtube-transcript-api）")
        return None

    langs = preferred_langs or _DEFAULT_PREFERRED_LANGS

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # 嘗試依語言偏好取得字幕
        transcript = None
        for lang in langs:
            try:
                transcript = transcript_list.find_transcript([lang])
                break
            except Exception:
                continue

        # 若偏好語言都沒有，嘗試取得任何可用字幕（含自動生成）
        if transcript is None:
            try:
                # 先嘗試手動字幕
                transcript = transcript_list.find_manually_created_transcript(
                    transcript_list._manually_created_transcripts.keys()
                )
            except Exception:
                pass

        if transcript is None:
            try:
                # 再嘗試自動生成字幕
                transcript = transcript_list.find_generated_transcript(
                    transcript_list._generated_transcripts.keys()
                )
            except Exception:
                pass

        if transcript is None:
            logger.debug("影片 %s 無任何可用字幕", video_id)
            return None

        # 將字幕片段拼接為純文字
        fetched = transcript.fetch()
        text = " ".join(segment.get("text", "") for segment in fetched)
        text = text.strip()

        if not text:
            return None

        # 截斷至 max_chars
        if len(text) > max_chars:
            text = text[:max_chars] + "…（字幕已截斷）"

        logger.debug("影片 %s 字幕擷取成功，%d 字元（語言：%s）", video_id, len(text), transcript.language_code)
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
