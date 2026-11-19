"""Cross-run memory store (Phase 3b, D36).

A workspace-scoped collection of path-addressed markdown documents that
survives across runs. Rebuilds the reference "memory stores" pattern on the
project's own storage: each memory is addressed by a forward-slash path, and
every change creates an immutable revision (append-only versions = audit
trail; earlier revisions are never modified, so consolidation can never
destroy its inputs).

Write discipline: runtime-only. The engine writes deterministic lesson
documents at run completion; `consolidate-memory` writes a merged revision
through an explicit live command. Roles read through the canonical memory
tools and never write.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from breakdown.canonical import digest_raw
from breakdown.models import MemoryDocument, MemorySummary

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_versions (
    path TEXT NOT NULL,
    revision INTEGER NOT NULL,
    content TEXT NOT NULL,
    digest TEXT NOT NULL,
    run_id TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (path, revision)
);
CREATE TABLE IF NOT EXISTS memories (
    path TEXT PRIMARY KEY,
    revision INTEGER NOT NULL,
    digest TEXT NOT NULL,
    run_id TEXT,
    created_at TEXT NOT NULL
);
"""


def validate_memory_path(raw: str) -> str:
    """Normalize a store-relative memory path or raise ValueError.

    Rejects empty/padded paths, backslashes, absolute paths, empty segments,
    and traversal — memory paths must stay inside the store.
    """
    if not raw or raw.strip() != raw:
        raise ValueError("memory path must be a non-empty, unpadded string")
    if "\\" in raw or "//" in raw:
        raise ValueError(f"memory path must use single forward slashes: {raw!r}")
    posix = PurePosixPath(raw)
    if posix.is_absolute() or ".." in posix.parts or "" in posix.parts:
        raise ValueError(f"memory path must be store-relative without traversal: {raw!r}")
    return posix.as_posix()


class MemoryStore:
    """SQLite-backed path-addressed documents with immutable revisions."""

    def __init__(self, root: Path) -> None:
        self.db_path = Path(root) / "memory.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        return conn

    def write(self, path: str, content: str, *, run_id: str | None = None) -> int:
        """Append a new immutable revision; returns the new revision number."""
        normalized = validate_memory_path(path)
        digest = digest_raw(content.encode("utf-8"))
        created_at = datetime.now(UTC).isoformat()
        conn = self._connect()
        try:
            with conn:
                row = conn.execute("SELECT revision FROM memories WHERE path = ?", (normalized,)).fetchone()
                revision = int(row["revision"]) + 1 if row is not None else 1
                conn.execute(
                    "INSERT INTO memory_versions (path, revision, content, digest, run_id, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (normalized, revision, content, digest, run_id, created_at),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO memories (path, revision, digest, run_id, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (normalized, revision, digest, run_id, created_at),
                )
            return revision
        finally:
            conn.close()

    def read(self, path: str, revision: int | None = None) -> MemoryDocument | None:
        """One revision (head when revision is None), or None if absent."""
        normalized = validate_memory_path(path)
        conn = self._connect()
        try:
            if revision is None:
                row = conn.execute(
                    "SELECT v.path, v.revision, v.content, v.digest, v.run_id, v.created_at "
                    "FROM memory_versions v JOIN memories m ON v.path = m.path AND v.revision = m.revision "
                    "WHERE v.path = ?",
                    (normalized,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT path, revision, content, digest, run_id, created_at "
                    "FROM memory_versions WHERE path = ? AND revision = ?",
                    (normalized, revision),
                ).fetchone()
            if row is None:
                return None
            return MemoryDocument(
                path=row["path"],
                revision=int(row["revision"]),
                digest=row["digest"],
                created_at=datetime.fromisoformat(row["created_at"]),
                content=row["content"],
                run_id=row["run_id"],
            )
        finally:
            conn.close()

    def list(self, prefix: str = "") -> tuple[MemorySummary, ...]:
        """Head summaries ordered by path, optionally filtered by prefix."""
        if prefix:
            validate_memory_path(prefix.rstrip("/"))
        conn = self._connect()
        try:
            escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            rows = conn.execute(
                "SELECT path, revision, digest, created_at FROM memories "
                "WHERE path LIKE ? ESCAPE '\\' ORDER BY path",
                (f"{escaped}%",),
            ).fetchall()
            return tuple(
                MemorySummary(
                    path=row["path"],
                    revision=int(row["revision"]),
                    digest=row["digest"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            )
        finally:
            conn.close()

    def search(self, pattern: str) -> tuple[MemorySummary, ...]:
        """Head revisions whose content matches the regex, ordered by path."""
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"invalid search pattern: {exc}") from exc
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT v.path, v.revision, v.digest, v.created_at, v.content "
                "FROM memory_versions v JOIN memories m ON v.path = m.path AND v.revision = m.revision "
                "ORDER BY v.path",
            ).fetchall()
            return tuple(
                MemorySummary(
                    path=row["path"],
                    revision=int(row["revision"]),
                    digest=row["digest"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
                if compiled.search(row["content"])
            )
        finally:
            conn.close()