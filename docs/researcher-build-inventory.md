# Build-Baseline Mapping & Normalization Researcher: Comprehensive Inventory & Blueprint

## 1. Executive Overview

This document establishes the comprehensive inventory and technical blueprint for rebuilding and expanding the **OneShot Breakdown Researcher** role. It bridges the clean-baseline foundation in `breakdown.yaml` with the seven Anthropic cookbook reference patterns, formalizing:
1. **Role Restructuring**: Reallocating Build-Baseline Mapping and Evidence Normalization ownership to the Researcher, with the Auditor providing independent governance review.
2. **Capability 1 — Embedding-Based Semantic Search**: Integrating Databricks AI Search (`breakdown_knowledge_index`) and hybrid tool retrieval.
3. **Capability 2 — Autonomous Tool Execution**: End-to-end tool loops via `OpenAICompatibleRoleBackend` and native Anthropic / Claude Agent SDK runners.
4. **Capability 3 — Async Multi-Agent Orchestration**: Hub-based message passing and bounded subagent delegation (`max_workers: 3, max_rounds: 3`).
5. **Capability 4 — Multi-Tier Hosting & Slack Bot**: Tier 1a (CLI batch), Tier 1b (FastAPI SSE), Tier 2 (Modal scale-to-zero), Tier 3 (Kubernetes), and a Socket Mode Slack Bot.
6. **Capability 5 — Cross-Session Memory Stores**: Persistent project baseline maps and shared evidence stores backed by SQLite CAS and memory store protocols.

---

## 2. Role Restructuring: Baseline Mapping & Evidence Normalization

### 2.1. Build-Baseline Mapping Ownership
* **Current State**: Stage 1 (`Auditor`) produces preliminary `candidate_source_responsibilities` based solely on initial requests.
* **Restructured Responsibility**:
  - The Researcher receives the approved research scope and target repository.
  - Using AST inspection, file reads, and semantic search, the Researcher produces an authoritative `BaselineMap`:
    - Full scaffolding inventory (directories, source modules, test fixtures, configuration).
    - File-to-responsibility mappings (`repo -> responsibility`).
    - Existing interface boundaries and public exports.
  - Stored as a durable artifact `baseline_map` and persisted into the project's memory store.

### 2.2. Evidence Normalization Ownership
* **Current State**: Stage 4 (`Auditor`) authors `normalized_evidence` and `classified_findings` from raw research responses.
* **Restructured Responsibility**:
  - The Researcher normalizes evidence during investigation, emitting typed `NormalizedEvidence` with verified provenance (source identity, location, version, access context).
  - The Researcher outputs pre-classified candidate findings (`ClassifiedFinding`).
  - The Auditor's `review_research_findings` transitions into an **independent verification and governance gate** that proves:
    1. Every finding traces directly to approved candidate requirements.
    2. Contradictions are preserved and not harmonized away.
    3. Unresolved questions remain transparently unhidden.
    4. No premature architecture or build tasks are introduced.

---

## 3. Five Advanced Capabilities Inventory

### Capability 1: Embedding-Based Semantic Tool & Repo Search
* **Primary Source**: *"Tool Search with Embeddings"*
* **Databricks Asset Utilization**:
  - **Endpoint**: `ai_search` (STANDARD, id: `6c87ebae-1878-44a0-b5d9-4d638912f685`)
  - **Index**: `workspace.default.breakdown_knowledge_index` (DELTA_SYNC, HYBRID)
  - **Source Table**: `workspace.default.breakdown_knowledge` (70 files, columns: `id`, `file_path`, `content`, `category`, `file_type`)
  - **Embedding Model**: `databricks-qwen3-embedding-0-6b` (1024 dimensions)
* **Implementation Artifacts**:
  - `breakdown/tools/semantic_search.py`: Canonical tool querying the index via `w.vector_search_endpoints.query_index()`, returning ranked file paths, symbol signatures, and code snippets.
  - `tool_search` meta-tool: Dynamic tool retrieval returning `tool_reference` blocks when tool catalogs scale.

### Capability 2: Autonomous Tool Use via Tool-Capable Runner
* **Primary Source**: *"Building a One-Liner Research Agent"* + *"Async Multi-Agent Orchestration"*
* **Core Architecture**:
  - Models autonomously drive the investigation loop: `model -> tool_call -> dispatch_tool -> tool_result -> next_turn` until all questions are addressed.
  - Multi-provider support in `breakdown/runners/`:
    - `OpenAICompatibleRoleBackend`: For Databricks Model Serving, custom OpenAI-compatible gateways, and local models.
    - `RawAnthropicRunner`: Direct `anthropic.AsyncAnthropic` client loop with native tool definitions and token streaming.
    - `ClaudeSDKClient`: Full Claude Agent SDK integration with managed subprocess environment.

### Capability 3: Async Multi-Agent Orchestration (Subagent Delegation)
* **Primary Source**: *"Async Multi-Agent Orchestration"*
* **Core Architecture**:
  - **Hub Message-Passing**: Shared in-memory event hub (`Hub`) with per-agent queues. Inboxes are automatically drained and attached to tool results — zero polling.
  - **Subagent Lifecycle Tools**:
    - `create_subagents(tasks: list[dict])`: Dynamically dispatches parallel sub-investigators per question.
    - `get_status(subagent_ids: list[str])`: Non-blocking lifecycle and progress inspection.
    - `kill_subagents(subagent_ids: list[str])`: Cleanup and cancellation.
  - **Delegation Guardrails** (governed by `breakdown.yaml` lines 356-361):
    - `default_workers: 1`
    - `maximum_parallel_workers: 3`
    - `maximum_delegation_rounds: 3`
    - `worker_access: read_only`
    - `worker_output_authority: evidence_input_only`

### Capability 4: Breakdown Bot & Runtime Lifecycle Invariants (D43 Refactored)
* **Primary Source**: Managed Agents Runtime & Async Lifecycle Cookbooks (Reference patterns, not build targets)
* **D43 Invariant Refactor (Supersedes Slack and Automations draft scaffolding)**:
  - References are guidance for planning and refactor, not source to copy. Slack socket mode bots and Automations draft wire format scaffolding are retired.
  - **Single Event-Loop Owner**: CLI calls `main()` synchronously; `WorkflowEngine._activate_with_timeout()` isolates coroutine execution via dedicated worker executor when an active event loop is detected, avoiding nested `asyncio.run()` collisions.
  - **Explicit Backend Close Lifecycle**: `aclose()` methods on `OpenAICompatibleRoleBackend` and `OpenAICompatibleCodingBackend` deterministically close underlying client connection pools on all exit paths (normal completion, cancellation, timeout, or crash).
  - **Explicit Runtime Kind**: `RunRecord.runtime_kind` explicitly records `offline_demo` vs `live_openai`; verified on resume to reject cross-backend resumption.
  - **Bounded Web Access**: Canonical `web_search` tool implemented with `httpx`, bounded by `allowed_domains`, `max_uses`, token cost calculation, and rejection of encrypted or binary payloads.
* **Breakdown Bot Architecture**:
  - Independent runtime in `breakdown/bot.py` and CLI `breakdown bot "<task>"`.
  - Intent resolution ("go research...", "go plan...", "implement..."), typed `BotEvent` streaming, interactive decision routing, and auto-approval capabilities.
  - Context managers (`__enter__`/`__exit__`, `__aenter__`/`__aexit__`) ensure deterministic lockfile release and resource disposal.

### Capability 5: Cross-Session Memory Stores
* **Primary Source**: *"Build agents that remember your users"* (Managed Agents Memory)
* **Durable Storage Topology**:
  - **Per-Project Baseline Map Store** (`read_write`): Persists project scaffolding, conventions, and file responsibilities across runs.
  - **Shared Evidence Store** (`read_only`): Persists verified external documentation, proven SDK behaviors, and historical findings.
  - Accessible via `breakdown/memory.py` SQLite CAS locally, and mounted to `/mnt/memory/` in hosted container sandboxes.

---

## 4. Component & File Inventory

| Component | Target Path | Responsibility |
|---|---|---|
| **Semantic Search Tool** | `breakdown/tools/semantic_search.py` | Query Databricks AI Search vector index |
| **Baseline Models** | `breakdown/models.py` | Declare `BaselineMap`, `ScaffoldingEntry`, `NormalizedEvidence` |
| **Researcher Agent** | `breakdown/roles/researcher.py` | Autonomous tool loop, subagent fan-out, baseline mapping |
| **Auditor Review Gate** | `breakdown/roles/auditor.py` | Lean governance verification of Researcher's pre-normalized findings |
| **Anthropic Runner** | `breakdown/runners/anthropic_runner.py` | Native tool-use loop over `AsyncAnthropic` |
| **Multi-Agent Hub** | `breakdown/orchestration/hub.py` | Async message passing and subagent supervisor |
| **Automations Engine** | `breakdown/automations.py` | Authoritative Automations draft YAML and proto wire format (D42) |
| **Breakdown Bot** | `breakdown/bot.py` | Event-driven bot runtime with trigger ingestion & action emission (D41, D42) |
| **Modal Sandbox** | `scripts/modal_researcher.py` | Tier 2 serverless deployment definition |

---

## 5. Execution & Rollout Roadmap

1. **Step 1: Data Models & Contracts**:
   - Add `BaselineMap` and `NormalizedEvidence` to `breakdown/models.py`.
   - Update `ResearchExecutionOutput` to carry `baseline_map` and pre-normalized evidence.
2. **Step 2: Semantic Search Tool Integration**:
   - Implement `breakdown/semantic_search.py` using Databricks Vector Search SDK with graceful offline fallback.
   - Register tool in `ROLE_TOOL_ALLOWLIST["researcher"]`.
3. **Step 3: Researcher Autonomous Engine & Subagents**:
   - Implement autonomous AST baseline mapping, normalization, and provenance validation in `breakdown/roles/researcher.py`.
4. **Step 4: Auditor Review Refinement**:
   - Update `Auditor.review_research_findings` to act as the independent verification gate for Researcher-emitted findings.
5. **Step 5: Automations Architecture & Trigger Ingestion (D42)**:
   - Implement `breakdown/automations.py` and integrate trigger routing into `breakdown/bot.py`.
   - Add `breakdown automation draft`, `validate`, and `breakdown bot --trigger` CLI commands.
6. **Step 6: Comprehensive Test Suite & Gate Verification**:
   - Add unit tests in `tests/test_automations.py`, `tests/test_bot.py`, `tests/test_roles.py`, `tests/test_memory.py`, and `tests/test_tools.py`.
   - Re-verify all 5 quality gates: `pytest`, `ruff check`, `mypy strict`, `--check`, and `python evals/run.py --offline`.
