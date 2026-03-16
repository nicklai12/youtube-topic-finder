"""YouTube Data API v3 封裝，含配額計算器。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from . import config

logger = logging.getLogger(__name__)

# YouTube API 各操作的配額成本
_QUOTA_COST = {
    "search.list": 100,
    "videos.list": 1,
}


class QuotaExceededError(Exception):
    """當本次執行已累計配額超過安全上限時拋出。"""


class YouTubeClient:
    def __init__(self, api_key: str) -> None:
        self._service = build("youtube", "v3", developerKey=api_key)
        self._units_used = 0

    # ── 公開方法 ──────────────────────────────────────────────────────────────

    def search_videos(
        self,
        keyword: str,
        published_within_days: int = config.SEARCH_PUBLISHED_WITHIN_DAYS,
        max_results: int = config.SEARCH_MAX_RESULTS,
    ) -> list[str]:
        """搜尋關鍵字，回傳影片 ID 列表。"""
        self._charge_quota("search.list")

        published_after = (
            datetime.now(timezone.utc) - timedelta(days=published_within_days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            response = (
                self._service.search()
                .list(
                    q=keyword,
                    part="id",
                    type="video",
                    order="viewCount",
                    publishedAfter=published_after,
                    maxResults=max_results,
                    relevanceLanguage="zh-Hant",
                )
                .execute()
            )
        except HttpError as exc:
            logger.error("search.list 失敗（%s）: %s", keyword, exc)
            return []

        video_ids = [
            item["id"]["videoId"]
            for item in response.get("items", [])
            if item.get("id", {}).get("kind") == "youtube#video"
        ]
        logger.info("關鍵字 '%s' 搜尋到 %d 支影片", keyword, len(video_ids))
        return video_ids

    def get_video_details(self, video_ids: list[str]) -> list[dict[str, Any]]:
        """批次取得影片詳情，每次最多 50 支。回傳標準化 dict 列表。"""
        if not video_ids:
            return []

        results: list[dict[str, Any]] = []
        # videos.list 每次最多 50 個 ID
        for chunk in _chunked(video_ids, 50):
            self._charge_quota("videos.list")
            try:
                response = (
                    self._service.videos()
                    .list(
                        id=",".join(chunk),
                        part="snippet,statistics,contentDetails",
                    )
                    .execute()
                )
            except HttpError as exc:
                logger.error("videos.list 失敗: %s", exc)
                continue

            for item in response.get("items", []):
                results.append(_normalize_video(item))

        return results

    @property
    def units_used(self) -> int:
        return self._units_used

    # ── 私有輔助 ──────────────────────────────────────────────────────────────

    def _charge_quota(self, operation: str) -> None:
        cost = _QUOTA_COST.get(operation, 0)
        if self._units_used + cost > config.MAX_UNITS_PER_RUN:
            raise QuotaExceededError(
                f"本次執行配額即將超過上限 {config.MAX_UNITS_PER_RUN} units "
                f"（已用 {self._units_used}，操作 {operation} 需 {cost}）"
            )
        self._units_used += cost
        logger.debug("配額使用：%s +%d → 累計 %d", operation, cost, self._units_used)


# ── 模組級工具函式 ─────────────────────────────────────────────────────────────

def _chunked(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def _normalize_video(item: dict[str, Any]) -> dict[str, Any]:
    """將 YouTube API 原始 item 轉為統一格式。"""
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})

    video_id = item["id"]
    published_at_str = snippet.get("publishedAt", "")
    try:
        published_at = datetime.fromisoformat(
            published_at_str.replace("Z", "+00:00")
        )
    except ValueError:
        published_at = datetime.now(timezone.utc)

    return {
        "video_id": video_id,
        "title": snippet.get("title", ""),
        "channel_id": snippet.get("channelId", ""),
        "channel_title": snippet.get("channelTitle", ""),
        "published_at": published_at,
        "thumbnail_url": (
            snippet.get("thumbnails", {}).get("high", {}).get("url", "")
            or snippet.get("thumbnails", {}).get("default", {}).get("url", "")
        ),
        "view_count": int(stats.get("viewCount") or 0),
        "like_count": int(stats.get("likeCount") or 0),
        "comment_count": int(stats.get("commentCount") or 0),
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "channel_url": f"https://www.youtube.com/channel/{snippet.get('channelId', '')}",
    }
