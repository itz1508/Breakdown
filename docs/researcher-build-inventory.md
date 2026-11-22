# Researcher Build-Baseline Mapping & Normalization

**Stage:** `research_execution` | **Path:** `breakdown/roles/researcher.py` | **Implemented:** yes | **Model:** any OpenAI-compatible custom API via `RoleBackend`

This document normalizes the Researcher's Build-Baseline Mapping and Evidence Normalization responsibilities. It describes what is implemented in `D:/Breakdown-tmp`, marks speculative items as not built, and cross-references `execplan_researcher_expansion.md` for the implementation log.

## Model connectivity

Breakdown is **model-agnostic**. Roles connect to models through the `RoleBackend` protocol (`breakdown/contracts.py`):

```python
@runtime_checkable
class RoleBackend(Protocol):
    async def generate(self, request: RoleBackendRequest) -> RoleBackendResponse: ...
```

Any custom API model works — there is **no Claude, no Anthropic, and no Modal lock-in**. Provider configuration uses `provider_id`, `protocol: openai_compatible`, `sdk`, `api_key_env`, and `base_url` to point at any OpenAI-compatible endpoint. Databricks (when `DATABRICKS_HOST`/`DATABRICKS_TOKEN` are configured) is used **only for semantic/vector search** (`breakdown/semantic_search.py`), never for model inference. Without Databricks credentials, `semantic_search` falls back to local lexical search over repository text.

## What is implemented

| Component | Path | Status |
|---|---|---|
| Data models | `breakdown/models.py` | `BaselineMap`, `ScaffoldingEntry`, `NormalizedEvidence` embedded in `ResearchRecord` (G1, G2) |
| Semantic search | `breakdown/semantic_search.py` | Dual-mode: Databricks Vector Search if configured, else local lexical fallback (G3) |
| Researcher role | `breakdown/roles/researcher.py` | AST baseline mapping, evidence normalization, provenance validation, coverage checks (G4) |
| Auditor review | `breakdown/roles/auditor.py` | Independent verification gate on pre-normalized findings (Task 4) |
| Memory helpers | `breakdown/memory.py` | `store_baseline_map`, `get_baseline_map` (G6, Task 5) |
| Breakdown Bot | `breakdown/bot.py`, CLI `breakdown bot` | Native bot runtime replacing external Slack bot (G5, Task 6) |
| Web search tool | `breakdown/tools.py` | Client-side `web_search` with `allowed_domains`, `max_uses`, cost calculation (Task 9) |

## Role restructuring (implemented)

**Baseline mapping ownership:** The Researcher produces an authoritative `BaselineMap` from the `SourceCheckpoint` — directory/module inventory, file-to-responsibility mappings, interface boundaries, public exports via AST inspection. Stored as `baseline_map` on `ResearchRecord`.

**Evidence normalization ownership:** The Researcher normalizes evidence during investigation, emitting typed `NormalizedEvidence` with `source_identity`, `source_location`, `source_version`, and `provenance_preserved`. The Auditor's `review_research_findings` acts as an independent verification gate: findings trace to approved requirements, contradictions are preserved, unresolved questions stay visible, no premature build tasks are introduced.

**Delegation bounded:** At most 3 parallel workers, 3 rounds, read-only, evidence input only. Synthetic samples never become evidence. No implementation or target paths are selected during research.

## Not built / deferred (speculative in original inventory)

These items were listed in the original blueprint but are **not implemented**:

- **Hub-based async multi-agent orchestration** (`max_workers: 3, max_rounds: 3` subagent fan-out) — deferred per execplan G4. Single-turn LLM call with provenance enforcement is the current scope.
- **Slack Bot / Socket Mode** — replaced by native `breakdown bot` CLI per execplan G5.
- **Databricks AI Search as primary model provider** — not implemented. Databricks is used only for optional semantic search; model inference uses `RoleBackend` with any OpenAI-compatible endpoint.
- **Kubernetes Tier 3 hosting, FastAPI SSE tier** — not in the implementation plan.
- **`breakdown/automations.py` Automations draft (D42)** — retired per D43, superseded by native Breakdown runtime lifecycle invariants.
- **`breakdown/runners/anthropic_runner.py` and `breakdown/orchestration/hub.py`** — do not exist; not part of current implementation.

## Path corrections

The original inventory referenced paths that do not match the implemented codebase:

| Original (incorrect) | Correct path |
|---|---|
| `breakdown/tools/semantic_search.py` | `breakdown/semantic_search.py` |
| `breakdown/runners/anthropic_runner.py` | does not exist |
| `breakdown/orchestration/hub.py` | does not exist |
| `breakdown/automations.py` | does not exist (retired per D43) |
| `scripts/modal_researcher.py` | does not exist |

## Relation to execplan

The implementation log is maintained in `D:/Breakdown-tmp/docs/execplan_researcher_expansion.md`. Gap-fix rounds (G1–G6, G19-1+) and Tasks 1–9 there record what was changed, why, and the named checks (`pytest`, `ruff`, `mypy`, `evals/run.py --offline`). This inventory document is the target-state reference; the execplan is the change log. Do not duplicate implementation detail across both.
