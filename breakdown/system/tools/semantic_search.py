"""Semantic search over target repository or Databricks AI Search vector index.

Dual-mode execution:
1. If Databricks Vector Search is configured and accessible, queries the
   provisioned vector search index (workspace.default.breakdown_knowledge_index).
2. Otherwise, falls back gracefully to local lexical/frequency scoring over text files
   strictly inside root, ensuring 100% offline test compliance.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from pydantic import Field
from breakdown.shared.models import StrictModel
from breakdown.system.safety import (
    is_denied_read_name,
    SKIPPED_DIR_NAMES,
)

MAX_FILE_BYTES = 1_000_000


class SemanticSearchRequest(StrictModel):
    query: str = Field(min_length=1)
    max_results: int = Field(default=10, ge=1, le=100)
    category: str | None = None


class SemanticSearchMatch(StrictModel):
    path: str
    snippet: str
    score: float = 0.0


class SemanticSearchReport(StrictModel):
    matches: tuple[SemanticSearchMatch, ...] = ()
    query: str
    mode: str = "lexical_fallback"


def _iter_searchable_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            continue
        if any(part in SKIPPED_DIR_NAMES for part in rel_parts):
            continue
        if is_denied_read_name(path.name):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        files.append(path)
    return files


def _local_lexical_search(payload: SemanticSearchRequest, *, root: Path) -> SemanticSearchReport:
    """Local lexical & TF ranking fallback when vector index is unavailable."""
    query_tokens = [w.lower() for w in re.findall(r"\w+", payload.query) if len(w) > 1]
    if not query_tokens:
        query_tokens = [payload.query.lower()]

    matches: list[SemanticSearchMatch] = []

    for file_path in _iter_searchable_files(root):
        try:
            text = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        rel_path = file_path.relative_to(root).as_posix()
        text_lower = text.lower()
        score = 0.0
        best_pos = -1

        for token in query_tokens:
            count = text_lower.count(token)
            if count > 0:
                score += float(count)
                pos = text_lower.find(token)
                if best_pos == -1 or (pos != -1 and pos < best_pos):
                    best_pos = pos

        if score > 0.0:
            # Extract excerpt
            if best_pos >= 0:
                start = max(0, best_pos - 60)
                end = min(len(text), best_pos + 200)
                snippet = text[start:end].strip().replace("\r", " ").replace("\n", " ")
            else:
                snippet = text[:200].strip().replace("\r", " ").replace("\n", " ")

            matches.append(
                SemanticSearchMatch(
                    path=rel_path,
                    snippet=snippet,
                    score=round(score, 2),
                )
            )

    matches.sort(key=lambda m: m.score, reverse=True)
    selected = matches[: payload.max_results]
    return SemanticSearchReport(
        matches=tuple(selected),
        query=payload.query,
        mode="lexical_fallback",
    )


def semantic_search(payload: SemanticSearchRequest, *, root: Path) -> SemanticSearchReport:
    """Execute semantic search against vector index or local fallback."""
    # Check if Databricks vector search environment is configured
    db_host = os.environ.get("DATABRICKS_HOST")
    db_token = os.environ.get("DATABRICKS_TOKEN")
    endpoint = os.environ.get("DATABRICKS_VECTOR_SEARCH_ENDPOINT", "ai_search")
    index_name = os.environ.get("DATABRICKS_VECTOR_INDEX", "workspace.default.breakdown_knowledge_index")

    if db_host and db_token:
        try:
            # Dynamic import of Databricks vector search client
            from databricks.vector_search.client import VectorSearchClient  # type: ignore[import-not-found]

            client: Any = VectorSearchClient(workspace_url=db_host, personal_access_token=db_token)
            index = client.get_index(endpoint_name=endpoint, index_name=index_name)
            results = index.similarity_search(
                query_text=payload.query,
                columns=["file_path", "content"],
                num_results=payload.max_results,
            )
            data_array = results.get("result", {}).get("data_array", [])
            matches = [
                SemanticSearchMatch(
                    path=str(row[0]),
                    snippet=str(row[1])[:300],
                    score=1.0,
                )
                for row in data_array
                if len(row) >= 2
            ]
            return SemanticSearchReport(
                matches=tuple(matches),
                query=payload.query,
                mode="vector",
            )
        except Exception:
            # Fall through to local fallback if remote vector search fails or library absent
            pass

    return _local_lexical_search(payload, root=root)
