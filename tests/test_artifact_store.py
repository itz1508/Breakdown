"""P2-T1 — artifact store: CAS, revisions, digest-verified reads."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from breakdown.artifact_store import (
    ArtifactNotFoundError,
    ArtifactStore,
    ArtifactStoreError,
    DigestMismatchError,
    DuplicateArtifactError,
    StaleRevisionError,
)
from breakdown.models import InitialRequest, RunRef


def _model(text: str = "hello") -> InitialRequest:
    return InitialRequest(text=text, created_at=datetime(2026, 11, 17, tzinfo=UTC))


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(tmp_path / ".breakdown")


def test_roundtrip_returns_validated_model(store: ArtifactStore) -> None:
    ref = store.store_artifact(_model(), "initial_request", contract_id="intake", contract_version="1")
    assert ref.revision == 1
    loaded = store.get_model(InitialRequest, "initial_request", ref.revision)
    assert loaded.text == "hello"
    assert store.get_digest("initial_request", 1) == ref.digest
    assert store.exists("initial_request", 1)


def test_revisions_append(store: ArtifactStore) -> None:
    first = store.store_artifact(_model("a"), "k", contract_id="c", contract_version="1")
    second = store.store_artifact(_model("b"), "k", contract_id="c", contract_version="1")
    assert (first.revision, second.revision) == (1, 2)
    assert store.latest_revision("k") == 2
    assert store.latest_revision("ghost") == 0


def test_put_immutable_idempotent_same_content(store: ArtifactStore) -> None:
    one = store.put_immutable(_model(), "k", 1, contract_id="c", contract_version="1")
    two = store.put_immutable(_model(), "k", 1, contract_id="c", contract_version="1")
    assert one == two


def test_put_immutable_rejects_different_content(store: ArtifactStore) -> None:
    store.put_immutable(_model("a"), "k", 1, contract_id="c", contract_version="1")
    with pytest.raises(DuplicateArtifactError):
        store.put_immutable(_model("b"), "k", 1, contract_id="c", contract_version="1")


def test_cas_conflict_and_success(store: ArtifactStore) -> None:
    store.store_artifact(_model("a"), "k", contract_id="c", contract_version="1")
    with pytest.raises(StaleRevisionError):
        store.put_cas(_model("x"), "k", 0, contract_id="c", contract_version="1")
    revision, _ = store.put_cas(_model("b"), "k", 1, contract_id="c", contract_version="1")
    assert revision == 2


def test_missing_artifact(store: ArtifactStore) -> None:
    with pytest.raises(ArtifactNotFoundError):
        store.get("ghost", 1)
    assert store.get_digest("ghost", 1) is None


def test_tampered_content_detected(store: ArtifactStore) -> None:
    ref = store.store_artifact(_model(), "k", contract_id="c", contract_version="1")
    conn = sqlite3.connect(store.db_path)
    try:
        conn.execute("UPDATE artifacts SET content = ? WHERE artifact_key = 'k'", (b"tampered",))
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(DigestMismatchError):
        store.get("k", ref.revision)


def test_schema_validation_on_read(store: ArtifactStore) -> None:
    ref = store.store_artifact(_model(), "k", contract_id="c", contract_version="1")
    with pytest.raises(ArtifactStoreError):
        store.get_model(RunRef, "k", ref.revision)
