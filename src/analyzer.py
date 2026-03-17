"""AI 分析模組：使用 Groq Llama 生成爆紅原因、內容摘要、二創角度建議。"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是一位 YouTube 內容分析師與二創策略顧問，專門分析爆紅影片並為內容創作者提供二創建議。"
    "請嚴格以 JSON 格式輸出分析結果，不要輸出任何 JSON 以外的內容。"
)

_USER_PROMPT_TEMPLATE = """\
以下是一支近期爆紅的 YouTube 影片資訊：
- 標題：{title}
- 頻道：{channel}
- 觀看次數：{views:,}
- 按讚數：{likes:,}
- 發布時間：{published}
{transcript_section}
請用**繁體中文**分析以下三個部分，並嚴格按照以下 JSON 格式輸出（不要輸出任何 JSON 以外的內容）：

{{
  "viral_reason": "（150 字以內）分析這支影片爆紅的可能原因，包含話題吸引力、標題設計、時機、受眾共鳴等面向",
  "summary": "（200 字以內）整理影片的核心內容與主要論點，讓沒看過的人能快速了解",
  "recreate_angles": [
    "二創角度 1：（具體可執行的切入點）",
    "二創角度 2：（具體可執行的切入點）",
    "二創角度 3：（具體可執行的切入點）"
  ]
}}
"""

_TRANSCRIPT_SECTION = """\
- 字幕內容（部分）：
---
{transcript}
---
"""

_NO_TRANSCRIPT_NOTE = "- 字幕：不可用（以下分析僅依據標題、頻道與觀看數據）\n"


def analyze_video(
    video: dict[str, Any],
    transcript: str | None,
    model: str = "moonshotai/kimi-k2-instruct-0905",
    api_key: str | None = None,
    transcript_source: str = "none",
) -> dict[str, Any] | None:
    """
    使用 Groq Llama 分析爆款影片，回傳結構化分析結果。

    Args:
        video: youtube_client.get_video_details() 回傳的影片資訊字典
        transcript: 影片字幕文字（由 transcript.get_transcript() 取得），無字幕時為 None
        model: Groq 模型名稱
        api_key: Groq API Key（若為 None 則從環境變數 GROQ_API_KEY 取得）
        transcript_source: 字幕來源，"youtube" / "whisper" / "none"

    Returns:
        包含 viral_reason / summary / recreate_angles / transcript_source 的字典；
        若無 API Key 或發生不可恢復的錯誤則回傳 None
    """
    key = api_key or os.environ.get("GROQ_API_KEY", "")
    if not key:
        logger.debug("GROQ_API_KEY 未設定，跳過 AI 分析")
        return None

    try:
        from groq import Groq
    except ImportError:
        logger.warning("groq 未安裝，無法執行 AI 分析（pip install groq）")
        return None

    # 組合 messages
    transcript_section = (
        _TRANSCRIPT_SECTION.format(transcript=transcript)
        if transcript
        else _NO_TRANSCRIPT_NOTE
    )

    published_str = video["published_at"].strftime("%Y-%m-%d")
    user_msg = _USER_PROMPT_TEMPLATE.format(
        title=video["title"],
        channel=video["channel_title"],
        views=video["view_count"],
        likes=video["like_count"],
        published=published_str,
        transcript_section=transcript_section,
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    max_retries = 3
    base_delay = 15  # 秒
    client = Groq(api_key=key)

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.4,
                max_tokens=1024,
            )

            raw = response.choices[0].message.content.strip()
            result = json.loads(raw)

            # 驗證必要欄位
            required = {"viral_reason", "summary", "recreate_angles"}
            if not required.issubset(result.keys()):
                logger.warning("影片 %s AI 分析結果缺少必要欄位: %s", video["video_id"], required - result.keys())
                return None

            if not isinstance(result["recreate_angles"], list):
                result["recreate_angles"] = [str(result["recreate_angles"])]

            result["transcript_source"] = transcript_source
            source_label = {"youtube": "字幕（YouTube）", "whisper": "字幕（Whisper）", "none": "無"}.get(transcript_source, "無")
            logger.info("影片 %s AI 分析完成（字幕：%s）", video["video_id"], source_label)
            return result

        except json.JSONDecodeError as exc:
            logger.warning("影片 %s AI 分析 JSON 解析失敗: %s", video["video_id"], exc)
            return None
        except Exception as exc:
            exc_str = str(exc)
            if "429" in exc_str or "rate_limit" in exc_str.lower() or "quota" in exc_str.lower():
                if attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "影片 %s AI 分析遇到速率限制，第 %d/%d 次重試，等待 %ds...",
                        video["video_id"], attempt, max_retries, delay,
                    )
                    time.sleep(delay)
                    continue
                logger.warning("影片 %s AI 分析已達最大重試次數，配額仍不足: %s", video["video_id"], exc)
            else:
                logger.warning("影片 %s AI 分析失敗: %s", video["video_id"], exc)
            return None

    return None
