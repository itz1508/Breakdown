"""Phase 3b — D36: cross-run memory store, canonical memory tools, containment.

Also covers D40: baseline_map persistence helpers (store_baseline_map / get_baseline_map).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from breakdown.shared.models import BaselineMap, MemoryDocument, ScaffoldingEntry
from breakdown.system.memory import MemoryStore, get_baseline_map, store_baseline_map, validate_memory_path
from breakdown.system.tools.toolkit import RoleToolkit
from breakdown.system.tools.tools import ToolNotAuthorized, dispatch_tool

def test_write_read_roundtrip(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    revision = store.write("lessons/run-1.md", "# lesson\nnever skip preflight", run_id="run-1")
    assert revision == 1
    document = store.read("lessons/run-1.md")
    assert document is not None
    assert document.path == "lessons/run-1.md"
    assert document.revision == 1
    assert document.content == "# lesson\nnever skip preflight"
    assert document.run_id == "run-1"
    assert len(document.digest) == 64  # sha256 hex
    assert document.created_at.tzinfo is not None


def test_revisions_are_immutable(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.write("notes.md", "original content", run_id="run-1")
    revision = store.write("notes.md", "updated content", run_id="run-2")
    assert revision == 2
    head = store.read("notes.md")
    old = store.read("notes.md", revision=1)
    assert head is not None and old is not None
    assert head.content == "updated content"
    assert head.run_id == "run-2"
    assert old.content == "original content"  # earlier revision untouched
    assert old.run_id == "run-1"
    assert head.digest != old.digest


def test_list_prefix_filtering_orders_by_path(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.write("runs/b.md", "b")
    store.write("lessons/a.md", "a")
    store.write("lessons/nested/c.md", "c")
    assert [s.path for s in store.list()] == ["lessons/a.md", "lessons/nested/c.md", "runs/b.md"]
    assert [s.path for s in store.list("lessons/")] == ["lessons/a.md", "lessons/nested/c.md"]
    assert store.list("ghost/") == ()


def test_search_matches_head_content_only(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.write("a.md", "the budget was exhausted at build stage")
    store.write("b.md", "all stages completed")
    store.write("a.md", "rewritten: topic changed entirely")  # head replaces match
    hits = store.search(r"budget")
    assert [s.path for s in hits] == []  # old revision's match is not searchable
    assert [s.path for s in store.search(r"stages|rewritten")] == ["a.md", "b.md"]
    with pytest.raises(ValueError, match="invalid search pattern"):
        store.search("([")


def test_read_missing_returns_none(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    assert store.read("ghost.md") is None
    store.write("real.md", "x")
    assert store.read("real.md", revision=99) is None


@pytest.mark.parametrize("bad", ["../escape.md", "/abs.md", "a\\b.md", "a//b.md", " padded.md", ""])
def test_path_validation_rejects_escapes(tmp_path: Path, bad: str) -> None:
    store = MemoryStore(tmp_path)
    with pytest.raises(ValueError):
        validate_memory_path(bad)
    with pytest.raises(ValueError):
        store.write(bad, "content")
    with pytest.raises(ValueError):
        store.read(bad)


def test_dispatch_memory_tools_and_allowlists(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.write("lessons/run-9.md", "always verify before sync", run_id="run-9")

    # Direct dispatch with a configured memory root works.
    document = dispatch_tool("memory_read", {"path": "lessons/run-9.md"}, root=tmp_path, memory_root=tmp_path)
    assert isinstance(document, MemoryDocument)
    assert document.content == "always verify before sync"
    listed = dispatch_tool("memory_list", {"prefix": "lessons/"}, root=tmp_path, memory_root=tmp_path)
    assert [s.path for s in listed] == ["lessons/run-9.md"]
    found = dispatch_tool("memory_search", {"pattern": "verify"}, root=tmp_path, memory_root=tmp_path)
    assert [s.path for s in found] == ["lessons/run-9.md"]

    # Reading a missing document is a tool error, not a crash.
    with pytest.raises(ValueError, match="memory not found"):
        dispatch_tool("memory_read", {"path": "ghost.md"}, root=tmp_path, memory_root=tmp_path)

    # The builder role gets no memory tools at all (D36).
    builder = RoleToolkit(role="builder", root=tmp_path, memory_root=tmp_path)
    assert builder.allowed_names() == ()
    with pytest.raises(ToolNotAuthorized, match="not allowed"):
        builder.call("memory_list", {})

    # Reading roles get them, but only when the store is configured.
    auditor = RoleToolkit(role="auditor", root=tmp_path, memory_root=None)
    with pytest.raises(ToolNotAuthorized, match="memory store not configured"):
        auditor.call("memory_list", {})
    configured = RoleToolkit(role="auditor", root=tmp_path, memory_root=tmp_path)
    result = configured.call("memory_read", {"path": "lessons/run-9.md"})
    assert result.content == "always verify before sync"
    for role in ("researcher", "coder", "planner"):
        assert set(RoleToolkit(role=role, root=tmp_path).allowed_names()) >= {
            "memory_list",
            "memory_read",
            "memory_search",
        }


# ---------------------------------------------------------------------------
# D40: baseline_map persistence helpers (store_baseline_map / get_baseline_map)
# ---------------------------------------------------------------------------


def _make_baseline(repo_id: str = "my-repo") -> BaselineMap:
    """Build a minimal valid BaselineMap for testing."""
    from datetime import UTC, datetime

    entry = ScaffoldingEntry(
        path="src/util.py",
        category="module",
        responsibility="Utility helpers",
        exports=("helper_fn",),
    )
    return BaselineMap(
        repository_identity=repo_id,
        entries=(entry,),
        created_at=datetime.now(UTC),
    )


def test_store_baseline_map_roundtrip(tmp_path: Path) -> None:
    """store_baseline_map writes JSON; get_baseline_map deserialises it back."""
    store = MemoryStore(tmp_path)
    baseline = _make_baseline("test-repo-alpha")

    revision = store_baseline_map(store, baseline, run_id="run-1")
    assert revision == 1, "first write should produce revision 1"

    recovered = get_baseline_map(store, "test-repo-alpha")
    assert recovered is not None, "baseline map should be found after storing"
    assert recovered.repository_identity == "test-repo-alpha"
    assert len(recovered.entries) == 1
    assert recovered.entries[0].path == "src/util.py"
    assert recovered.entries[0].responsibility == "Utility helpers"


def test_get_baseline_map_returns_none_when_missing(tmp_path: Path) -> None:
    """get_baseline_map returns None for an unseen repository identity."""
    store = MemoryStore(tmp_path)
    result = get_baseline_map(store, "ghost-repo")
    assert result is None


def test_store_baseline_map_latest_revision_wins(tmp_path: Path) -> None:
    """Storing a new baseline for the same repo ID creates a new revision; get returns head."""
    from datetime import UTC, datetime

    store = MemoryStore(tmp_path)
    baseline_v1 = _make_baseline("versioned-repo")

    entry_v2 = ScaffoldingEntry(
        path="src/engine.py",
        category="module",
        responsibility="Core engine",
        exports=("Engine",),
    )
    baseline_v2 = BaselineMap(
        repository_identity="versioned-repo",
        entries=(entry_v2,),
        created_at=datetime.now(UTC),
    )

    rev1 = store_baseline_map(store, baseline_v1, run_id="run-1")
    rev2 = store_baseline_map(store, baseline_v2, run_id="run-2")
    assert rev2 == rev1 + 1, "second store should increment revision"

    head = get_baseline_map(store, "versioned-repo")
    assert head is not None
    # Head should reflect the second (latest) baseline
    assert len(head.entries) == 1
    assert head.entries[0].path == "src/engine.py"
