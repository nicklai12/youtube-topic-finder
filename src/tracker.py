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

# tracking.json 中 Whisper 用量記錄的頂層 key
_WHISPER_USAGE_KEY = "_whisper_usage"


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
    """更新或新建某影片的追蹤記錄，並維護 stale_count。"""
    now = datetime.now(timezone.utc).isoformat()
    existing = data.get(video_id)

    if existing is None:
        # 新記錄
        data[video_id] = {
            "view_count": view_count,
            "updated_at": now,
            "stale_count": 0,
        }
        return

    last_views = existing.get("view_count", 0)
    growth_rate = (view_count - last_views) / last_views if last_views > 0 else None

    # 成長率低於閾值 → stale_count +1；否則重置
    if growth_rate is not None and growth_rate < config.AUTO_CLOSE_GROWTH_BELOW:
        stale_count = existing.get("stale_count", 0) + 1
    else:
        stale_count = 0

    data[video_id] = {
        "view_count": view_count,
        "updated_at": now,
        "stale_count": stale_count,
    }


def purge_expired(data: dict[str, Any]) -> int:
    """移除超過 TRACKING_EXPIRY_DAYS 天未更新的記錄，回傳刪除筆數。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.TRACKING_EXPIRY_DAYS)
    expired = []
    for key, record in data.items():
        if key == _WHISPER_USAGE_KEY:
            continue  # 獨立清理，後面操作
        updated_at_str = record.get("updated_at", "")
        try:
            updated_at = datetime.fromisoformat(updated_at_str)
            if updated_at < cutoff:
                expired.append(key)
        except (ValueError, TypeError):
            expired.append(key)

    for key in expired:
        del data[key]

    _purge_whisper_usage(data)

    if expired:
        logger.info("清理過期追蹤記錄 %d 筆。", len(expired))
    return len(expired)


def get_whisper_usage_today(data: dict[str, Any]) -> float:
    """回傳今日已使用的 Whisper 音訊秒數。"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return data.get(_WHISPER_USAGE_KEY, {}).get(today, {}).get("total_seconds", 0.0)


def update_whisper_usage(data: dict[str, Any], duration_sec: float) -> None:
    """對今日的 Whisper 用量累加 duration_sec 秒。"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    usage = data.setdefault(_WHISPER_USAGE_KEY, {})
    day = usage.setdefault(today, {"total_seconds": 0.0, "count": 0})
    day["total_seconds"] = round(day["total_seconds"] + duration_sec, 2)
    day["count"] += 1


def _purge_whisper_usage(data: dict[str, Any]) -> None:
    """移除超過 7 天的 Whisper 用量日期記錄。"""
    usage = data.get(_WHISPER_USAGE_KEY)
    if not usage:
        return
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    old_dates = [d for d in list(usage.keys()) if d < cutoff_date]
    for d in old_dates:
        del usage[d]
