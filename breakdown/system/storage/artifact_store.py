"""Content-addressed artifact store (SQLite CAS + revisions).

Ported from ``d:\\breakdown\\system\\storage\\artifact_store.py``:
immutable (artifact_key, revision) pairs holding canonical bytes, digests
verified before read, compare-and-swap writes for mutable slots. Logical
keys are workflow artifact keys; physical storage is runtime-owned
(artifact_keys.physical_path_assignment in breakdown.yaml).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from breakdown.shared.models import ArtifactRef
from breakdown.system.storage.canonical import SERIALIZER_PROFILE, canonical_bytes, digest_raw

T = TypeVar("T", bound=BaseModel)


class ArtifactStoreError(RuntimeError):
    pass


class DuplicateArtifactError(ArtifactStoreError):
    pass


class ArtifactNotFoundError(ArtifactStoreError):
    pass


class DigestMismatchError(ArtifactStoreError):
    """Stored bytes no longer match their recorded digest."""


class StaleRevisionError(ArtifactStoreError):
    pass


class ArtifactStore:
    """Immutable content-addressed store; one SQLite database per state root."""

    def __init__(self, state_root: str | Path) -> None:
        self.state_root = Path(state_root)
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_root / "artifacts.db"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_key TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    digest TEXT NOT NULL,
                    contract_id TEXT NOT NULL,
                    contract_version TEXT NOT NULL,
                    serializer_profile TEXT NOT NULL,
                    content BLOB NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (artifact_key, revision)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def put_immutable(
        self,
        model: BaseModel,
        artifact_key: str,
        revision: int,
        *,
        contract_id: str,
        contract_version: str,
    ) -> str:
        """Store at an exact revision. Idempotent for identical content;
        raises DuplicateArtifactError if the slot holds different bytes."""
        content = canonical_bytes(model)
        digest = digest_raw(content)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT digest FROM artifacts WHERE artifact_key = ? AND revision = ?",
                (artifact_key, revision),
            ).fetchone()
            if row is not None:
                if row[0] != digest:
                    raise DuplicateArtifactError(
                        f"artifact {artifact_key} rev {revision} exists with a different digest"
                    )
                conn.execute("COMMIT")
                return str(row[0])
            conn.execute(
                "INSERT INTO artifacts ("
                "artifact_key, revision, digest, contract_id, contract_version, "
                "serializer_profile, content) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (artifact_key, revision, digest, contract_id, contract_version, SERIALIZER_PROFILE, content),
            )
            conn.execute("COMMIT")
            return digest
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def store_artifact(
        self, model: BaseModel, artifact_key: str, *, contract_id: str, contract_version: str
    ) -> ArtifactRef:
        """Append the next revision and return a reference (never bytes)."""
        revision = self.latest_revision(artifact_key) + 1
        digest = self.put_immutable(
            model, artifact_key, revision, contract_id=contract_id, contract_version=contract_version
        )
        return ArtifactRef(artifact_key=artifact_key, digest=digest, revision=revision)

    def put_cas(
        self,
        model: BaseModel,
        artifact_key: str,
        expected_revision: int,
        *,
        contract_id: str,
        contract_version: str,
    ) -> tuple[int, str]:
        """Atomic compare-and-swap write at expected_revision + 1."""
        content = canonical_bytes(model)
        digest = digest_raw(content)
        new_revision = expected_revision + 1
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT MAX(revision) FROM artifacts WHERE artifact_key = ?", (artifact_key,)).fetchone()
            current = row[0] or 0
            if current != expected_revision:
                raise StaleRevisionError(
                    f"CAS failed for {artifact_key}: expected rev {expected_revision}, found {current}"
                )
            conn.execute(
                "INSERT INTO artifacts ("
                "artifact_key, revision, digest, contract_id, contract_version, "
                "serializer_profile, content) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (artifact_key, new_revision, digest, contract_id, contract_version, SERIALIZER_PROFILE, content),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return new_revision, digest

    def get(self, artifact_key: str, revision: int) -> bytes:
        """Read content after re-verifying its digest
        (artifact_rules: digest_verified_before_read)."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT digest, content FROM artifacts WHERE artifact_key = ? AND revision = ?",
                (artifact_key, revision),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise ArtifactNotFoundError(f"artifact {artifact_key} rev {revision} not found")
        recorded_digest, content = row
        if digest_raw(bytes(content)) != recorded_digest:
            raise DigestMismatchError(f"artifact {artifact_key} rev {revision} failed digest verification")
        return bytes(content)

    def get_model(self, model_type: type[T], artifact_key: str, revision: int) -> T:
        raw = self.get(artifact_key, revision)
        try:
            data: Any = json.loads(raw.decode("utf-8"))
            return model_type.model_validate(data)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
            raise ArtifactStoreError(f"artifact {artifact_key} rev {revision} failed schema validation: {exc}") from exc

    def get_digest(self, artifact_key: str, revision: int) -> str | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT digest FROM artifacts WHERE artifact_key = ? AND revision = ?",
                (artifact_key, revision),
            ).fetchone()
        finally:
            conn.close()
        return None if row is None else str(row[0])

    def latest_revision(self, artifact_key: str) -> int:
        conn = self._connect()
        try:
            row = conn.execute("SELECT MAX(revision) FROM artifacts WHERE artifact_key = ?", (artifact_key,)).fetchone()
        finally:
            conn.close()
        return int(row[0] or 0)

    def exists(self, artifact_key: str, revision: int) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM artifacts WHERE artifact_key = ? AND revision = ?",
                (artifact_key, revision),
            ).fetchone()
        finally:
            conn.close()
        return row is not None
