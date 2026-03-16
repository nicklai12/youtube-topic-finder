"""爆款判定邏輯：結合觀看門檻條件與短期成長率條件。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import config


def is_viral(
    video: dict[str, Any],
    growth_rate: float | None,
) -> tuple[bool, str]:
    """
    判斷影片是否為爆款。

    Args:
        video: youtube_client._normalize_video() 回傳的標準化 dict。
        growth_rate: tracker.get_growth_rate() 的計算結果，None 表示無歷史數據。

    Returns:
        (True, reason_str) 若符合爆款條件；(False, "") 若不符合。
    """
    now = datetime.now(timezone.utc)
    published_at: datetime = video["published_at"]
    view_count: int = video["view_count"]

    # 確保 published_at 為 aware datetime
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)

    age_hours = (now - published_at).total_seconds() / 3600
    age_days = age_hours / 24

    # 門檻條件 1：發布 N 小時內觀看超過 M
    fast = config.THRESHOLD_FAST
    if age_hours <= fast["hours"] and view_count >= fast["views"]:
        views_fmt = _fmt_views(view_count)
        return (
            True,
            f"發布 {int(age_hours)} 小時內已累積 {views_fmt} 觀看次數"
            f"（門檻：{fast['hours']}hr / {_fmt_views(fast['views'])}）",
        )

    # 門檻條件 2：發布 N 天內觀看超過 M
    slow = config.THRESHOLD_SLOW
    if age_days <= slow["days"] and view_count >= slow["views"]:
        views_fmt = _fmt_views(view_count)
        return (
            True,
            f"發布 {int(age_days)} 天內已累積 {views_fmt} 觀看次數"
            f"（門檻：{slow['days']}天 / {_fmt_views(slow['views'])}）",
        )

    # 成長條件：本次與上次記錄相比，成長率超過閾值
    if growth_rate is not None and growth_rate >= config.GROWTH_RATE_THRESHOLD:
        pct = int(growth_rate * 100)
        views_fmt = _fmt_views(view_count)
        return (
            True,
            f"6 小時內觀看數成長 {pct}%（當前 {views_fmt} 觀看）",
        )

    return (False, "")


def _fmt_views(n: int) -> str:
    """將觀看數格式化為易讀字串，例如 1,234,567 → 123.5萬。"""
    if n >= 10_000_000:
        return f"{n / 10_000_000:.1f}千萬"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}百萬"
    if n >= 10_000:
        return f"{n / 10_000:.1f}萬"
    return f"{n:,}"
