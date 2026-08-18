from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class ConversationStore:
    """Small local store for development; replaceable by SQLiteSession/Redis later."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_events (
                    user_id TEXT NOT NULL,
                    usage_date TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

    def history(self, conversation_id: str, limit: int = 8) -> list[dict[str, str]]:
        connection = sqlite3.connect(self.path)
        try:
            rows = connection.execute(
                """
                SELECT role, content
                FROM conversation_messages
                WHERE conversation_id=?
                ORDER BY rowid DESC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
        finally:
            connection.close()
        return [{"role": role, "content": content} for role, content in reversed(rows)]

    def append(self, conversation_id: str, role: str, content: str) -> None:
        connection = sqlite3.connect(self.path)
        try:
            connection.execute(
                """
                INSERT INTO conversation_messages(conversation_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, role, content, datetime.now(timezone.utc).isoformat()),
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def usage_today(self, user_id: str) -> int:
        connection = sqlite3.connect(self.path)
        try:
            row = connection.execute(
                "SELECT COUNT(*) FROM usage_events WHERE user_id=? AND usage_date=?",
                (user_id, self._today()),
            ).fetchone()
            return int(row[0] if row else 0)
        finally:
            connection.close()

    def consume_usage(self, user_id: str, daily_limit: int | None) -> tuple[bool, int]:
        """Atomically reserve one request and return (allowed, used_count)."""
        connection = sqlite3.connect(self.path, timeout=5)
        today = self._today()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT COUNT(*) FROM usage_events WHERE user_id=? AND usage_date=?",
                (user_id, today),
            ).fetchone()
            used = int(row[0] if row else 0)
            if daily_limit is not None and used >= daily_limit:
                connection.rollback()
                return False, used
            connection.execute(
                "INSERT INTO usage_events(user_id, usage_date, created_at) VALUES (?, ?, ?)",
                (user_id, today, datetime.now(timezone.utc).isoformat()),
            )
            connection.commit()
            return True, used + 1
        finally:
            connection.close()
