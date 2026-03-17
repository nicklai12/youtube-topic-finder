"""GitHub Issue 管理：建立爆款影片 Issue、去重、更新統計留言。"""

from __future__ import annotations

import logging
import re
from datetime import timezone
from typing import Any

from github import Github, GithubException
from github.Repository import Repository

logger = logging.getLogger(__name__)

# 嵌入 Issue body 的隱藏錨點，用於去重識別（不影響顯示）
_MARKER_TPL = "<!-- video_id: {video_id} -->"
_MARKER_RE = re.compile(r"<!-- video_id: ([\w-]+) -->")

# GitHub Issue Labels（若不存在會自動建立）
_LABEL_META = {
    "viral":           {"color": "e11d48", "description": "爆款影片"},
    "tech":            {"color": "6366f1", "description": "科技/程式類"},
    "finance":         {"color": "16a34a", "description": "財經/投資類"},
    "view-threshold":  {"color": "f97316", "description": "觀看門檻觸發"},
    "growth-spike":    {"color": "a855f7", "description": "成長率觸發"},
}


class IssueManager:
    def __init__(self, github_token: str, repo_full_name: str) -> None:
        self._gh = Github(github_token)
        self._repo: Repository = self._gh.get_repo(repo_full_name)
        self._ensure_labels()
        # 預先載入所有 open issues 的 video_id，避免逐一呼叫 Search API 觸發頻率限制
        self._open_issue_map: dict[str, int] = {}  # video_id -> issue number
        self._load_open_issues()

    # ── 公開方法 ──────────────────────────────────────────────────────────────

    def find_existing_issue(self, video_id: str) -> bool:
        """回傳此影片是否已有 Issue（依預載的快取查詢）。"""
        return video_id in self._open_issue_map

    def close_stale_issue(self, video_id: str) -> bool:
        """關閉指定 video_id 的 Issue（觀看數不再成長時呼叫）。回傳是否成功關閉。"""
        issue_number = self._open_issue_map.get(video_id)
        if issue_number is None:
            return False
        try:
            issue = self._repo.get_issue(issue_number)
            issue.create_comment("📉 觀看數已連續多次檢查無明顯成長，自動關閉此 Issue。")
            issue.edit(state="closed")
            logger.info("Issue #%d 已自動關閉（影片 %s 觀看數停滯）", issue.number, video_id)
            del self._open_issue_map[video_id]
            return True
        except GithubException as exc:
            logger.warning("關閉 Issue 失敗（%s）: %s", video_id, exc)
        return False

    def create_issue(
        self,
        video: dict[str, Any],
        viral_reason: str,
        topic_label: str,
        growth_rate: float | None,
        analysis: dict[str, Any] | None = None,
    ) -> None:
        """為爆款影片建立 GitHub Issue。"""
        title = f"🔥 {video['title']}"
        body = _build_body(video, viral_reason, growth_rate, analysis)
        labels = _pick_labels(topic_label, viral_reason)

        try:
            issue = self._repo.create_issue(
                title=title,
                body=body,
                labels=labels,
            )
            logger.info("Issue #%d 已建立：%s", issue.number, video["title"])
            self._open_issue_map[video["video_id"]] = issue.number
        except GithubException as exc:
            logger.error("建立 Issue 失敗（%s）: %s", video["video_id"], exc)

    # ── 私有輔助 ──────────────────────────────────────────────────────────────

    def _load_open_issues(self) -> None:
        """一次性載入所有帶 viral label 的 open issues，提取 video_id 建立快取。"""
        try:
            open_issues = self._repo.get_issues(state="open", labels=["viral"])
            for issue in open_issues:
                match = _MARKER_RE.search(issue.body or "")
                if match:
                    self._open_issue_map[match.group(1)] = issue.number
            logger.info("已載入 %d 筆已存在的 viral Issues", len(self._open_issue_map))
        except GithubException as exc:
            logger.warning("載入 open issues 失敗: %s", exc)

    def _ensure_labels(self) -> None:
        """確保所有需要的 Labels 存在於 repo，不存在則自動建立。"""
        existing = {label.name for label in self._repo.get_labels()}
        for name, meta in _LABEL_META.items():
            if name not in existing:
                try:
                    self._repo.create_label(
                        name=name,
                        color=meta["color"],
                        description=meta["description"],
                    )
                    logger.info("已建立 Label：%s", name)
                except GithubException as exc:
                    logger.warning("建立 Label '%s' 失敗: %s", name, exc)


# ── 模組級工具函式 ─────────────────────────────────────────────────────────────

def _build_body(
    video: dict[str, Any],
    viral_reason: str,
    growth_rate: float | None,
    analysis: dict[str, Any] | None = None,
) -> str:
    published_at = video["published_at"]
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    published_str = published_at.strftime("%Y-%m-%d %H:%M UTC")

    view_count = video["view_count"]
    like_count = video["like_count"]
    growth_str = f"{int(growth_rate * 100)}%" if growth_rate is not None else "N/A（首次發現）"

    marker = _MARKER_TPL.format(video_id=video["video_id"])

    base = f"""## 影片資訊

[![縮圖]({video['thumbnail_url']})]({video['url']})

| 欄位 | 內容 |
|------|------|
| **連結** | [{video['title']}]({video['url']}) |
| **頻道** | [{video['channel_title']}]({video['channel_url']}) |
| **發布時間** | {published_str} |
| **觀看次數** | {view_count:,} |
| **按讚數** | {like_count:,} |
| **本次成長率** | {growth_str} |

## 🔥 爆款原因

{viral_reason}

---

{marker}
"""

    if analysis is None:
        return base

    angles_md = "\n".join(
        f"{i + 1}. {angle}" for i, angle in enumerate(analysis.get("recreate_angles", []))
    )
    source_map = {"youtube": "YouTube 字幕", "whisper": "Whisper 語音轉文字", "none": "僅 metadata"}
    source_note = source_map.get(analysis.get("transcript_source", "none"), "僅 metadata")

    ai_section = f"""## 🤖 AI 分析

### 爆紅原因
{analysis.get('viral_reason', '')}

### 內容摘要
{analysis.get('summary', '')}

### 💡 二創角度建議
{angles_md}

> ℹ️ 分析由 Kimi K2 (Groq) 自動生成，僅供參考。字幕來源：{source_note}
"""

    # 在 marker 前插入 AI 區塊
    return base.replace(f"---\n\n{marker}", f"---\n\n{ai_section}\n---\n\n{marker}")


def _pick_labels(topic_label: str, viral_reason: str) -> list[str]:
    labels = ["viral", topic_label]
    if "成長" in viral_reason:
        labels.append("growth-spike")
    else:
        labels.append("view-threshold")
    return labels
