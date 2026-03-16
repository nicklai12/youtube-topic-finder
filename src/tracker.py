"""讀寫 data/tracking.json，計算觀看成長率，清理過期記錄。"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from . import config

logger = logging.getLogger(__name__)

_TRACKING_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "tracking.json"
)


def load() -> dict[str, Any]:
    """載入 tracking.json；若不存在則回傳空 dict。"""
    path = os.path.abspath(_TRACKING_PATH)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            logger.warning("tracking.json 格式錯誤，重置為空。")
            return {}


def save(data: dict[str, Any]) -> None:
    """將 tracking data 寫回 tracking.json。"""
    path = os.path.abspath(_TRACKING_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    logger.debug("tracking.json 已更新，共 %d 筆記錄。", len(data))


def get_growth_rate(video_id: str, current_views: int, data: dict[str, Any]) -> float | None:
    """
    計算影片從上次記錄到現在的觀看成長率。

    回傳：
      - float：成長率（0.5 = 50%，1.0 = 100%）
      - None：沒有上次記錄，無法比較
    """
    record = data.get(video_id)
    if record is None:
        return None

    last_views = record.get("view_count", 0)
    if last_views == 0:
        return None

    return (current_views - last_views) / last_views


def update_record(video_id: str, view_count: int, data: dict[str, Any]) -> None:
    """更新或新建某影片的追蹤記錄。"""
    data[video_id] = {
        "view_count": view_count,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def purge_expired(data: dict[str, Any]) -> int:
    """移除超過 TRACKING_EXPIRY_DAYS 天未更新的記錄，回傳刪除筆數。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.TRACKING_EXPIRY_DAYS)
    expired = []
    for video_id, record in data.items():
        updated_at_str = record.get("updated_at", "")
        try:
            updated_at = datetime.fromisoformat(updated_at_str)
            if updated_at < cutoff:
                expired.append(video_id)
        except (ValueError, TypeError):
            expired.append(video_id)

    for video_id in expired:
        del data[video_id]

    if expired:
        logger.info("清理過期追蹤記錄 %d 筆。", len(expired))
    return len(expired)
