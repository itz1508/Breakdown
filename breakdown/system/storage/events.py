"""Append-only run event log (SQLite).

Ported pattern from ``d:\\breakdown\\system\\storage\\event_store.py``,
typed against ``WorkflowEvent``. Persistent event types are durable;
ephemeral types (``activity_updated``) are never written to the log —
they exist for live display only. Log lines are canonical JSON with a
stored digest, verified on read.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from breakdown.shared.models import EventPersistence, EventType, WorkflowEvent
from breakdown.system.storage.canonical import canonical_bytes_from_dict, digest_raw

class EventStoreError(RuntimeError):
    pass


class EventStore:
    def __init__(self, state_root: str | Path) -> None:
        self.state_root = Path(state_root)
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_root / "events.db"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_digest TEXT NOT NULL,
                    event_data TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id)")
            conn.commit()
        finally:
            conn.close()

    def append(self, event: WorkflowEvent) -> int:
        """Persist one event; returns its sequence number."""
        if event.persistence is EventPersistence.EPHEMERAL:
            raise EventStoreError(f"ephemeral event {event.event_type.value} is never persisted")
        payload = canonical_bytes_from_dict(event.model_dump(mode="json"))
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                "INSERT INTO events (run_id, event_type, event_digest, event_data, occurred_at) VALUES (?, ?, ?, ?, ?)",
                (
                    event.run_id,
                    event.event_type.value,
                    digest_raw(payload),
                    payload.decode("utf-8"),
                    event.occurred_at.isoformat(),
                ),
            )
            conn.execute("COMMIT")
            return cursor.lastrowid or 0
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def emit(
        self,
        event_type: EventType,
        *,
        run_id: str,
        stage_id: str | None = None,
        attempt: int | None = None,
        payload: Mapping[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> int:
        event = WorkflowEvent(
            event_type=event_type,
            run_id=run_id,
            stage_id=stage_id,
            attempt=attempt,
            payload=dict(payload or {}),
            occurred_at=occurred_at or datetime.now(UTC),
        )
        return self.append(event)

    def list_raw(self, run_id: str, after: int = 0, limit: int | None = None) -> list[dict[str, Any]]:
        if after < 0 or (limit is not None and limit < 1):
            raise EventStoreError("invalid event history cursor or page size")
        query = (
            "SELECT seq, event_type, event_digest, event_data, occurred_at "
            "FROM events WHERE run_id = ? AND seq > ? ORDER BY seq"
        )
        params: list[Any] = [run_id, after]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        conn = self._connect()
        try:
            rows = conn.execute(query, params).fetchall()
        finally:
            conn.close()
        return [
            {"seq": r[0], "event_type": r[1], "event_digest": r[2], "event_data": r[3], "occurred_at": r[4]}
            for r in rows
        ]

    def load(self, run_id: str, after: int = 0, limit: int | None = None) -> tuple[WorkflowEvent, ...]:
        """Read typed events back, verifying each line's digest."""
        events: list[WorkflowEvent] = []
        for row in self.list_raw(run_id, after=after, limit=limit):
            event = WorkflowEvent.model_validate_json(row["event_data"])
            recomputed = digest_raw(canonical_bytes_from_dict(event.model_dump(mode="json")))
            if recomputed != row["event_digest"]:
                raise EventStoreError(f"event seq {row['seq']} failed digest verification")
            events.append(event)
        return tuple(events)
