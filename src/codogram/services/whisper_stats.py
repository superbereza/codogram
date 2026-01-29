"""Whisper usage statistics service."""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from ..logging_config import logger

WHISPER_LOG_PATH = Path.home() / ".codogram" / "whisper-usage.jsonl"


@dataclass
class StatsEntry:
    """Single aggregated stats entry."""
    name: str  # username or project name
    cost_usd: float
    count: int


@dataclass
class StatsResult:
    """Aggregated statistics result."""
    entries: list[StatsEntry]
    total_cost: float
    total_count: int


class WhisperStatsService:
    """Service for aggregating Whisper usage statistics."""

    def get_stats(self, view: str, period: str) -> StatsResult:
        """Get aggregated stats by view (users/projects) and period (7d/30d/all)."""
        entries = self._load_entries(period)

        if view == "users":
            return self._aggregate_by_users(entries)
        return self._aggregate_by_projects(entries)

    def _load_entries(self, period: str) -> list[dict]:
        """Load JSONL entries filtered by period."""
        if not WHISPER_LOG_PATH.exists():
            return []

        cutoff = self._get_cutoff(period)
        entries = []

        try:
            with open(WHISPER_LOG_PATH) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        # Filter by success and period
                        if not entry.get("success", False):
                            continue
                        if cutoff:
                            ts = datetime.fromisoformat(entry["ts"])
                            if ts < cutoff:
                                continue
                        entries.append(entry)
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.debug(f"Skipping invalid log entry: {e}")
                        continue
        except Exception as e:
            logger.warning(f"Failed to read whisper log: {e}")

        return entries

    def _get_cutoff(self, period: str) -> datetime | None:
        """Get cutoff datetime for period filter."""
        now = datetime.now()
        if period == "7d":
            return now - timedelta(days=7)
        if period == "30d":
            return now - timedelta(days=30)
        return None  # "all" - no cutoff

    def _aggregate_by_users(self, entries: list[dict]) -> StatsResult:
        """Aggregate entries by user."""
        # Group by user_id, keep latest username
        user_data: dict[int, dict] = {}

        for entry in entries:
            user_id = entry.get("user_id", 0)
            if user_id not in user_data:
                user_data[user_id] = {
                    "username": entry.get("username"),
                    "cost": 0.0,
                    "count": 0,
                }
            user_data[user_id]["cost"] += entry.get("cost_usd", 0)
            user_data[user_id]["count"] += 1
            # Update username if available (might be added later)
            if entry.get("username"):
                user_data[user_id]["username"] = entry["username"]

        # Build result
        stats_entries = []
        for user_id, data in user_data.items():
            name = f"@{data['username']}" if data["username"] else f"id:{user_id}"
            stats_entries.append(StatsEntry(
                name=name,
                cost_usd=data["cost"],
                count=data["count"],
            ))

        # Sort by cost descending
        stats_entries.sort(key=lambda x: x.cost_usd, reverse=True)

        total_cost = sum(e.cost_usd for e in stats_entries)
        total_count = sum(e.count for e in stats_entries)

        return StatsResult(
            entries=stats_entries,
            total_cost=total_cost,
            total_count=total_count,
        )

    def _aggregate_by_projects(self, entries: list[dict]) -> StatsResult:
        """Aggregate entries by project."""
        project_data: dict[str, dict] = {}

        for entry in entries:
            project = entry.get("project") or "(unknown)"
            if project not in project_data:
                project_data[project] = {"cost": 0.0, "count": 0}
            project_data[project]["cost"] += entry.get("cost_usd", 0)
            project_data[project]["count"] += 1

        # Build result
        stats_entries = []
        for project, data in project_data.items():
            stats_entries.append(StatsEntry(
                name=project,
                cost_usd=data["cost"],
                count=data["count"],
            ))

        # Sort by cost descending
        stats_entries.sort(key=lambda x: x.cost_usd, reverse=True)

        total_cost = sum(e.cost_usd for e in stats_entries)
        total_count = sum(e.count for e in stats_entries)

        return StatsResult(
            entries=stats_entries,
            total_cost=total_cost,
            total_count=total_count,
        )
