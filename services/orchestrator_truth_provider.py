#!/usr/bin/env python3
"""
Orchestrator Truth Provider — Real data for Home Console inbox, runs, overview.

Consumes canonical SSOT artifacts and maps them to Home Console data models.
No fake data. No mock data.
"""

from datetime import datetime
from typing import List, Optional
from pathlib import Path

from services.mission_truth_provider import MissionTruthProvider


# Re-use data models from home_console_page.py for consistency
# We import them lazily to avoid circular imports at module load time


def _parse_iso(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.now()


def _source_to_icon(source: str) -> str:
    mapping = {
        "email_personal": "mail-unread-symbolic",
        "email_business": "mail-unread-symbolic",
        "github": "system-software-install-symbolic",
        "discord": "user-available-symbolic",
        "slack": "user-available-symbolic",
        "youtube_comment": "video-display-symbolic",
        "ops_alert": "dialog-warning-symbolic",
        "orchestrator": "system-run-symbolic",
        "stackkraft": "media-playback-start-symbolic",
    }
    return mapping.get(source, "emblem-default-symbolic")


class OrchestratorTruthProvider:
    """Provides real inbox threads, runs, and overview for the Home Console."""

    @classmethod
    def get_inbox_threads(cls) -> List[dict]:
        """Return inbox threads mapped from canonical sources."""
        threads = []
        for item in MissionTruthProvider.get_inbox_threads():
            threads.append({
                "id": item["id"],
                "source": item["source"],
                "source_icon": _source_to_icon(item["source"]),
                "identity": "mindsong",  # All operational items are MindSong-branded
                "sender": item["sender"],
                "preview": item["preview"],
                "bucket": "now" if item["priority"] == 0 else "queued",
                "priority": item["priority"],
                "timestamp": _parse_iso(item.get("timestamp", "")),
                "unread": True,
                "suggested_action": item.get("suggested_action", "Review"),
            })
        return threads

    @classmethod
    def get_runs(cls) -> List[dict]:
        """Return execution runs from active campaigns."""
        runs = []
        for item in MissionTruthProvider.get_runs():
            status = item.get("status", "queued")
            started = item.get("started_at", "")
            runs.append({
                "id": item["id"],
                "name": item["name"],
                "type": item.get("type", "orchestrator"),
                "status": status,
                "started_at": _parse_iso(started) if started else None,
                "progress_pct": item.get("progress_pct"),
                "can_cancel": item.get("can_cancel", False),
                "owner": item.get("owner", ""),
                "source": item.get("source", ""),
                "receipt_path": item.get("receipt_path", ""),
            })
        return runs

    @classmethod
    def get_overview(cls) -> dict:
        """Quick status overview."""
        return MissionTruthProvider.get_overview()
