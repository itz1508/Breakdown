"""Run state store (SQLite, CAS-guarded).

Ported pattern from ``d:\\breakdown\\system\\storage\\checkpoint_store.py``
(compare-and-swap revisions, competing-writer rejection). Holds
``RunRecord`` — the durable lifecycle state of each workflow run. The
pinned definition triple is immutable after run start
(definition.mutation_after_run_start: prohibited).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from breakdown.canonical import canonical_bytes_from_dict, digest_raw
from breakdown.models import RunRecord


class RunStoreError(RuntimeError):
    pass


class CompetingWriterError(RunStoreError):
    pass


class RunNotFoundError(RunStoreError):
    pass


class DefinitionPinError(RunStoreError):
    """The pinned definition triple may never change after run start."""


class RunStore:
    def __init__(self, state_root: str | Path) -> None:
        self.state_root = Path(state_root)
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_root / "runs.db"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    record_digest TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def create_run(self, record: RunRecord) -> int:
        if self.load(record.run_id) is not None:
            raise RunStoreError(f"run {record.run_id} already exists")
        payload = canonical_bytes_from_dict(record.model_dump(mode="json"))
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO runs (run_id, revision, record_digest, record_json, created_at, updated_at) "
                "VALUES (?, 1, ?, ?, ?, ?)",
                (
                    record.run_id,
                    digest_raw(payload),
                    payload.decode("utf-8"),
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
            conn.execute("COMMIT")
            return 1
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def load(self, run_id: str) -> tuple[int, RunRecord] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT revision, record_digest, record_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        revision, recorded_digest, raw = row
        record = RunRecord.model_validate_json(raw)
        if digest_raw(canonical_bytes_from_dict(record.model_dump(mode="json"))) != recorded_digest:
            raise RunStoreError(f"run {run_id} failed digest verification")
        return int(revision), record

    def update_run(self, record: RunRecord, expected_revision: int) -> int:
        """CAS state transition; rejects competing writers and any mutation
        of the pinned definition triple."""
        loaded = self.load(record.run_id)
        if loaded is None:
            raise RunNotFoundError(f"run {record.run_id} does not exist")
        current_revision, previous = loaded
        if current_revision != expected_revision:
            raise CompetingWriterError(
                f"CAS failed for run {record.run_id}: expected rev {expected_revision}, found {current_revision}"
            )
        pinned = (previous.workflow_id, previous.definition_version, previous.definition_digest)
        candidate = (record.workflow_id, record.definition_version, record.definition_digest)
        if pinned != candidate:
            raise DefinitionPinError(f"run {record.run_id}: definition pin is immutable after run start")
        stamped = record.model_copy(update={"updated_at": datetime.now(UTC)})
        payload = canonical_bytes_from_dict(stamped.model_dump(mode="json"))
        new_revision = current_revision + 1
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                "UPDATE runs SET revision = ?, record_digest = ?, record_json = ?, updated_at = ? "
                "WHERE run_id = ? AND revision = ?",
                (
                    new_revision,
                    digest_raw(payload),
                    payload.decode("utf-8"),
                    stamped.updated_at.isoformat(),
                    record.run_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise CompetingWriterError(f"run {record.run_id} was updated by a competing writer")
            conn.execute("COMMIT")
            return new_revision
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def list_runs(self) -> tuple[str, ...]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT run_id FROM runs ORDER BY created_at").fetchall()
        finally:
            conn.close()
        return tuple(str(row[0]) for row in rows)
