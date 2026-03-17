"""AI 分析模組：使用 Gemini Flash 生成爆紅原因、內容摘要、二創角度建議。"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
你是一位 YouTube 內容分析師與二創策略顧問，專門分析爆紅影片並為內容創作者提供二創建議。

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
    model: str = "gemini-2.0-flash",
    api_key: str | None = None,
) -> dict[str, Any] | None:
    """
    使用 Gemini Flash 分析爆款影片，回傳結構化分析結果。

    Args:
        video: youtube_client.get_video_details() 回傳的影片資訊字典
        transcript: 影片字幕文字（由 transcript.get_transcript() 取得），無字幕時為 None
        model: Gemini 模型名稱
        api_key: Gemini API Key（若為 None 則從環境變數 GEMINI_API_KEY 取得）

    Returns:
        包含 viral_reason / summary / recreate_angles / has_transcript 的字典；
        若無 API Key 或發生不可恢復的錯誤則回傳 None
    """
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        logger.debug("GEMINI_API_KEY 未設定，跳過 AI 分析")
        return None

    try:
        import google.generativeai as genai
    except ImportError:
        logger.warning("google-generativeai 未安裝，無法執行 AI 分析（pip install google-generativeai）")
        return None

    # 組合 prompt
    transcript_section = (
        _TRANSCRIPT_SECTION.format(transcript=transcript)
        if transcript
        else _NO_TRANSCRIPT_NOTE
    )

    published_str = video["published_at"].strftime("%Y-%m-%d")
    prompt = _PROMPT_TEMPLATE.format(
        title=video["title"],
        channel=video["channel_title"],
        views=video["view_count"],
        likes=video["like_count"],
        published=published_str,
        transcript_section=transcript_section,
    )

    max_retries = 3
    base_delay = 15  # 秒

    for attempt in range(1, max_retries + 1):
        try:
            genai.configure(api_key=key)
            client = genai.GenerativeModel(model)
            response = client.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.4,
                    max_output_tokens=1024,
                ),
            )

            raw = response.text.strip()

            # 擷取 JSON（有時模型會在 JSON 前後加 markdown code fence）
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not json_match:
                logger.warning("影片 %s AI 分析回傳格式異常，無法解析 JSON", video["video_id"])
                return None

            result = json.loads(json_match.group())

            # 驗證必要欄位
            required = {"viral_reason", "summary", "recreate_angles"}
            if not required.issubset(result.keys()):
                logger.warning("影片 %s AI 分析結果缺少必要欄位: %s", video["video_id"], required - result.keys())
                return None

            if not isinstance(result["recreate_angles"], list):
                result["recreate_angles"] = [str(result["recreate_angles"])]

            result["has_transcript"] = transcript is not None
            logger.info("影片 %s AI 分析完成（字幕：%s）", video["video_id"], "有" if transcript else "無")
            return result

        except json.JSONDecodeError as exc:
            logger.warning("影片 %s AI 分析 JSON 解析失敗: %s", video["video_id"], exc)
            return None
        except Exception as exc:
            exc_str = str(exc)
            if "429" in exc_str or "quota" in exc_str.lower():
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
