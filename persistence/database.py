"""
SQLite persistence layer.
Uses aiosqlite for fully async non-blocking I/O.
Schema is created automatically on first use.
"""

from __future__ import annotations
import json
import logging
from datetime import datetime
from typing import Optional

import aiosqlite

from core.models import (
    Email,
    EmailProcessingResult,
    ProcessingStatus,
    SpamLabel,
    PriorityLevel,
    DecisionAction,
)
from config.settings import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()

_DDL = """
CREATE TABLE IF NOT EXISTS emails (
    id           TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    message_id   TEXT,
    thread_id    TEXT,
    subject      TEXT NOT NULL,
    sender       TEXT NOT NULL,
    recipients   TEXT NOT NULL,   -- JSON array
    body         TEXT NOT NULL,
    received_at  TEXT NOT NULL,
    labels       TEXT,            -- JSON array
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS processing_results (
    id                  TEXT PRIMARY KEY,
    email_id            TEXT NOT NULL REFERENCES emails(id),
    processed_at        TEXT NOT NULL,
    status              TEXT NOT NULL,

    -- Spam
    spam_label          TEXT,
    spam_confidence     REAL,
    spam_reasoning      TEXT,
    spam_indicators     TEXT,   -- JSON array

    -- Priority
    priority_level      TEXT,
    priority_score      REAL,
    priority_reasoning  TEXT,
    priority_tags       TEXT,   -- JSON array

    -- Decision
    decision_action     TEXT,
    decision_reasoning  TEXT,
    decision_confidence REAL,
    should_reply        INTEGER,
    forward_to          TEXT,

    -- Auto-reply
    reply_generated     INTEGER,
    reply_subject       TEXT,
    reply_body          TEXT,
    reply_tone          TEXT,

    processing_time_ms  REAL,
    error               TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_results_email_id   ON processing_results(email_id);
CREATE INDEX IF NOT EXISTS idx_results_status     ON processing_results(status);
CREATE INDEX IF NOT EXISTS idx_results_spam_label ON processing_results(spam_label);
CREATE INDEX IF NOT EXISTS idx_results_priority   ON processing_results(priority_level);
CREATE INDEX IF NOT EXISTS idx_results_action     ON processing_results(decision_action);
"""


class Database:
    """Async SQLite database manager."""

    def __init__(self, db_path: str | None = None) -> None:
        self._path = db_path or settings.db_path
        self._conn: Optional[aiosqlite.Connection] = None

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_DDL)
        await self._conn.commit()
        logger.info("데이터베이스 연결됨: %s", self._path)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def __aenter__(self) -> "Database":
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    # ── Email CRUD ──────────────────────────────────────────────────────────

    async def upsert_email(self, email: Email) -> None:
        assert self._conn, "Not connected"
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO emails
              (id, source, message_id, thread_id, subject, sender,
               recipients, body, received_at, labels)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                email.id,
                email.source.value,
                email.message_id,
                email.thread_id,
                email.subject,
                email.sender,
                json.dumps(email.recipients),
                email.body,
                email.received_at.isoformat(),
                json.dumps(email.labels),
            ),
        )
        await self._conn.commit()

    # ── Result CRUD ─────────────────────────────────────────────────────────

    async def save_result(self, result: EmailProcessingResult) -> None:
        assert self._conn, "Not connected"

        s = result.spam
        p = result.priority
        d = result.decision
        r = result.auto_reply

        await self._conn.execute(
            """
            INSERT OR REPLACE INTO processing_results (
                id, email_id, processed_at, status,
                spam_label, spam_confidence, spam_reasoning, spam_indicators,
                priority_level, priority_score, priority_reasoning, priority_tags,
                decision_action, decision_reasoning, decision_confidence,
                should_reply, forward_to,
                reply_generated, reply_subject, reply_body, reply_tone,
                processing_time_ms, error
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                result.id,
                result.email_id,
                result.processed_at.isoformat(),
                result.status.value,
                # spam
                s.label.value         if s else None,
                s.confidence          if s else None,
                s.reasoning           if s else None,
                json.dumps(s.indicators) if s else None,
                # priority
                p.level.value         if p else None,
                p.score               if p else None,
                p.reasoning           if p else None,
                json.dumps(p.tags)    if p else None,
                # decision
                d.action.value        if d else None,
                d.reasoning           if d else None,
                d.confidence          if d else None,
                int(d.should_reply)   if d else None,
                d.forward_to          if d else None,
                # reply
                int(r.generated)      if r else None,
                r.subject             if r else None,
                r.body                if r else None,
                r.tone                if r else None,
                result.processing_time_ms,
                result.error,
            ),
        )
        await self._conn.commit()

    # ── Queries ─────────────────────────────────────────────────────────────

    async def get_result(self, result_id: str) -> Optional[dict]:
        assert self._conn, "Not connected"
        async with self._conn.execute(
            "SELECT * FROM processing_results WHERE id = ?", (result_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_results_for_email(self, email_id: str) -> list[dict]:
        assert self._conn, "Not connected"
        async with self._conn.execute(
            "SELECT * FROM processing_results WHERE email_id = ? ORDER BY processed_at DESC",
            (email_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def list_results(
        self,
        status: Optional[ProcessingStatus] = None,
        spam_label: Optional[SpamLabel] = None,
        priority_level: Optional[PriorityLevel] = None,
        action: Optional[DecisionAction] = None,
        limit: int = 100,
    ) -> list[dict]:
        assert self._conn, "Not connected"
        clauses, params = [], []
        if status:
            clauses.append("status = ?");         params.append(status.value)
        if spam_label:
            clauses.append("spam_label = ?");     params.append(spam_label.value)
        if priority_level:
            clauses.append("priority_level = ?"); params.append(priority_level.value)
        if action:
            clauses.append("decision_action = ?"); params.append(action.value)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        async with self._conn.execute(
            f"SELECT * FROM processing_results {where} ORDER BY processed_at DESC LIMIT ?",
            params,
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_stats(self) -> dict:
        assert self._conn, "Not connected"
        stats: dict = {}
        for label in ("spam", "not_spam", "suspect"):
            async with self._conn.execute(
                "SELECT COUNT(*) FROM processing_results WHERE spam_label = ?", (label,)
            ) as cur:
                row = await cur.fetchone()
                stats[f"spam_{label}"] = row[0] if row else 0

        for level in ("critical", "high", "medium", "low"):
            async with self._conn.execute(
                "SELECT COUNT(*) FROM processing_results WHERE priority_level = ?", (level,)
            ) as cur:
                row = await cur.fetchone()
                stats[f"priority_{level}"] = row[0] if row else 0

        async with self._conn.execute(
            "SELECT COUNT(*) FROM processing_results WHERE status = 'completed'"
        ) as cur:
            row = await cur.fetchone()
            stats["total_completed"] = row[0] if row else 0

        async with self._conn.execute(
            "SELECT AVG(processing_time_ms) FROM processing_results WHERE status = 'completed'"
        ) as cur:
            row = await cur.fetchone()
            stats["avg_processing_time_ms"] = round(row[0] or 0, 2)

        return stats
