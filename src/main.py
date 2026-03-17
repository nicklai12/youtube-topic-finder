"""主入口：串接搜尋、爆款判定、Issue 建立、tracking 更新。"""

from __future__ import annotations

import logging
import os
import sys

from . import config, tracker
from .analyzer import analyze_video
from .issue_manager import IssueManager
from .transcript import get_transcript
from .viral_detector import is_viral
from .youtube_client import QuotaExceededError, YouTubeClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    # ── 讀取環境變數 ──────────────────────────────────────────────────────────
    youtube_api_key = os.environ.get("YOUTUBE_API_KEY", "")
    github_token = os.environ.get("GITHUB_TOKEN", "")
    github_repo = os.environ.get("GITHUB_REPOSITORY", "")

    if not youtube_api_key:
        logger.error("環境變數 YOUTUBE_API_KEY 未設定，請在 Secrets 中設定後再執行。")
        sys.exit(1)
    if not github_token:
        logger.error("環境變數 GITHUB_TOKEN 未設定。")
        sys.exit(1)
    if not github_repo:
        logger.error("環境變數 GITHUB_REPOSITORY 未設定（通常由 Actions 自動提供）。")
        sys.exit(1)

    # ── 初始化 ────────────────────────────────────────────────────────────────
    groq_api_key = os.environ.get("GROQ_API_KEY", "")
    yt = YouTubeClient(youtube_api_key)
    im = IssueManager(github_token, github_repo)
    tracking_data = tracker.load()

    issues_created = 0
    videos_checked = 0
    youtube_transcript_count = 0
    whisper_count = 0
    whisper_total_seconds = 0.0
    whisper_used_today = tracker.get_whisper_usage_today(tracking_data)

    # ── 主迴圈：遍歷所有主題與關鍵字 ─────────────────────────────────────────
    for topic_key, topic_cfg in config.TOPICS.items():
        topic_label = topic_cfg["label"]
        keywords = topic_cfg["keywords"]

        # 收集此主題所有關鍵字搜出的影片 ID（去重）
        all_video_ids: set[str] = set()
        for keyword in keywords:
            try:
                ids = yt.search_videos(keyword)
                all_video_ids.update(ids)
            except QuotaExceededError as exc:
                logger.warning("配額已達上限，停止搜尋：%s", exc)
                break

        logger.info("主題 '%s' 共收集到 %d 支不重複影片 ID", topic_key, len(all_video_ids))

        if not all_video_ids:
            continue

        # 批次取得影片詳情
        try:
            videos = yt.get_video_details(list(all_video_ids))
        except QuotaExceededError as exc:
            logger.warning("配額已達上限，跳過取詳情：%s", exc)
            break

        videos_checked += len(videos)

        # 逐支影片判斷是否爆款
        for video in videos:
            video_id = video["video_id"]
            view_count = video["view_count"]

            growth_rate = tracker.get_growth_rate(video_id, view_count, tracking_data)
            viral, reason = is_viral(video, growth_rate)

            # 更新追蹤記錄（無論是否爆款都記錄，以便下次計算成長率）
            tracker.update_record(video_id, view_count, tracking_data)

            if not viral:
                continue

            # 去重：已有 Issue 則跳過
            if im.find_existing_issue(video_id):
                logger.info("影片 %s 已有 Issue，跳過。", video_id)
                continue

            # AI 分析（字幕 + Groq）
            analysis = None
            if config.ANALYZER_ENABLED:
                whisper_ok = (config.WHISPER_ENABLED
                              and (whisper_used_today < config.WHISPER_DAILY_LIMIT_SECONDS))
                if config.WHISPER_ENABLED and not whisper_ok:
                    logger.warning(
                        "Whisper 今日用量已達 %d 秒（上限 %d 秒），此影片降級為 metadata 分析",
                        int(whisper_used_today), config.WHISPER_DAILY_LIMIT_SECONDS,
                    )
                tr = get_transcript(
                    video_id,
                    preferred_langs=config.ANALYZER_PREFERRED_LANGS,
                    max_chars=config.ANALYZER_MAX_TRANSCRIPT_CHARS,
                    whisper_enabled=whisper_ok,
                    whisper_model=config.WHISPER_MODEL,
                    max_audio_duration_minutes=config.MAX_AUDIO_DURATION_MINUTES,
                    groq_api_key=groq_api_key,
                )
                if tr.source == "youtube":
                    youtube_transcript_count += 1
                elif tr.source == "whisper":
                    whisper_count += 1
                    dur = tr.audio_duration_sec or 0.0
                    whisper_total_seconds += dur
                    whisper_used_today += dur
                    tracker.update_whisper_usage(tracking_data, dur)
                analysis = analyze_video(
                    video,
                    tr.text,
                    model=config.ANALYZER_MODEL,
                    transcript_source=tr.source,
                )

            im.create_issue(video, reason, topic_label, growth_rate, analysis)
            issues_created += 1

    # ── 清理過期記錄並儲存 ────────────────────────────────────────────────────
    tracker.purge_expired(tracking_data)
    tracker.save(tracking_data)

    # ── 自動關閉觀看數停滯的 Issue ────────────────────────────────────────────
    issues_closed = 0
    if config.AUTO_CLOSE_ENABLED:
        for video_id, record in tracking_data.items():
            stale_count = record.get("stale_count", 0)
            if stale_count >= config.AUTO_CLOSE_STALE_COUNT:
                if im.close_stale_issue(video_id):
                    issues_closed += 1
                    # 重置 stale_count 避免下次重複觸發
                    record["stale_count"] = 0
        if issues_closed:
            tracker.save(tracking_data)

    # ── 執行摘要 ──────────────────────────────────────────────────────────────
    whisper_min = int(whisper_total_seconds / 60)
    used_today_min = int(whisper_used_today / 60)
    limit_min = config.WHISPER_DAILY_LIMIT_SECONDS // 60
    logger.info(
        "執行完畢｜檢查影片：%d 支｜新建 Issue：%d 個｜關閉 Issue：%d 個｜"
        "API 配額消耗：%d units｜"
        "YouTube 字幕：%d 支｜Whisper：%d 支（共 %d 分鐘）｜今日累計 %d/%d 分鐘",
        videos_checked, issues_created, issues_closed, yt.units_used,
        youtube_transcript_count, whisper_count, whisper_min,
        used_today_min, limit_min,
    )


if __name__ == "__main__":
    main()
