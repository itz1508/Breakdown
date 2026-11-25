"""P2-T3 — run store: CAS transitions, definition pin, digest verification."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from breakdown.shared.models import RunRecord, RunState
from breakdown.system.storage.run_store import (
    CompetingWriterError,
    DefinitionPinError,
    RunNotFoundError,
    RunStore,
    RunStoreError,
)

def _record(run_id: str = "run-1", **overrides: Any) -> RunRecord:
    payload: dict[str, Any] = {
        "run_id": run_id,
        "session_id": "s-1",
        "workflow_id": "oneshot.breakdown",
        "definition_version": 1,
        "definition_digest": "0" * 64,
        "created_at": datetime(2026, 11, 17, tzinfo=UTC),
        "updated_at": datetime(2026, 11, 17, tzinfo=UTC),
    }
    payload.update(overrides)
    return RunRecord.model_validate(payload)


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / ".breakdown")


def test_create_and_load(store: RunStore) -> None:
    assert store.create_run(_record()) == 1
    loaded = store.load("run-1")
    assert loaded is not None
    revision, record = loaded
    assert revision == 1
    assert record.state is RunState.CREATED


def test_duplicate_create_rejected(store: RunStore) -> None:
    store.create_run(_record())
    with pytest.raises(RunStoreError):
        store.create_run(_record())


def test_cas_update_advances_revision(store: RunStore) -> None:
    store.create_run(_record())
    updated = _record(state=RunState.RUNNING, current_stage="research_proposal")
    assert store.update_run(updated, expected_revision=1) == 2
    revision, record = store.load("run-1")
    assert revision == 2
    assert record.state is RunState.RUNNING
    assert record.current_stage == "research_proposal"


def test_stale_revision_rejected(store: RunStore) -> None:
    store.create_run(_record())
    store.update_run(_record(state=RunState.RUNNING), expected_revision=1)
    with pytest.raises(CompetingWriterError):
        store.update_run(_record(state=RunState.TERMINAL), expected_revision=1)


def test_definition_pin_immutable(store: RunStore) -> None:
    store.create_run(_record())
    with pytest.raises(DefinitionPinError):
        store.update_run(_record(definition_digest="f" * 64), expected_revision=1)
    with pytest.raises(DefinitionPinError):
        store.update_run(_record(definition_version=2), expected_revision=1)


def test_update_missing_run(store: RunStore) -> None:
    with pytest.raises(RunNotFoundError):
        store.update_run(_record(run_id="ghost"), expected_revision=1)


def test_tampered_record_detected(store: RunStore) -> None:
    store.create_run(_record())
    conn = sqlite3.connect(store.db_path)
    try:
        conn.execute("UPDATE runs SET record_json = REPLACE(record_json, 'oneshot.breakdown', 'evil.workflow')")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(RunStoreError):
        store.load("run-1")


def test_list_runs(store: RunStore) -> None:
    store.create_run(_record(run_id="b"))
    store.create_run(_record(run_id="a"))
    assert set(store.list_runs()) == {"a", "b"}
