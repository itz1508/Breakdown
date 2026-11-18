"""P2-T2 — event log: persistence split, ordering, pagination, tamper rows."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from breakdown.events import EventStore, EventStoreError
from breakdown.models import EventType, WorkflowEvent


@pytest.fixture
def store(tmp_path: Path) -> EventStore:
    return EventStore(tmp_path / ".breakdown")


def test_append_and_load_roundtrip(store: EventStore) -> None:
    seq = store.emit(EventType.STAGE_ENTERED, run_id="run-1", stage_id="research_proposal")
    assert seq == 1
    events = store.load("run-1")
    assert len(events) == 1
    assert events[0].event_type is EventType.STAGE_ENTERED
    assert events[0].stage_id == "research_proposal"


def test_ephemeral_events_never_persisted(store: EventStore) -> None:
    with pytest.raises(EventStoreError):
        store.append(
            WorkflowEvent(
                event_type=EventType.ACTIVITY_UPDATED,
                run_id="run-1",
                occurred_at=datetime.now(UTC),
            )
        )
    assert store.list_raw("run-1") == []


def test_ordering_and_cursor_pagination(store: EventStore) -> None:
    for index in range(5):
        store.emit(EventType.ARTIFACT_PRODUCED, run_id="run-1", payload={"index": index})
    page_one = store.list_raw("run-1", after=0, limit=2)
    assert [row["seq"] for row in page_one] == [1, 2]
    page_two = store.list_raw("run-1", after=2, limit=2)
    assert [row["seq"] for row in page_two] == [3, 4]
    rest = store.load("run-1", after=4)
    assert len(rest) == 1


def test_invalid_cursor_rejected(store: EventStore) -> None:
    with pytest.raises(EventStoreError):
        store.list_raw("run-1", after=-1)
    with pytest.raises(EventStoreError):
        store.list_raw("run-1", limit=0)


def test_runs_are_isolated(store: EventStore) -> None:
    store.emit(EventType.STAGE_ENTERED, run_id="run-1")
    store.emit(EventType.STAGE_ENTERED, run_id="run-2")
    assert len(store.load("run-1")) == 1
    assert len(store.load("run-2")) == 1


def test_tampered_event_detected(store: EventStore) -> None:
    store.emit(EventType.STAGE_COMPLETED, run_id="run-1", stage_id="research_proposal")
    conn = sqlite3.connect(store.db_path)
    try:
        conn.execute("UPDATE events SET event_data = REPLACE(event_data, 'research_proposal', 'build_execution')")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(EventStoreError):
        store.load("run-1")
