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

### Capability 4: Multi-Tier Hosting & Slack Bot Integration
* **Primary Source**: *"Hosting the Agent"* + Slack App Manifest
* **Standardized Tier Structure**:
  - **Tier 1a (Ephemeral Batch)**: `run_once.py` CLI script executing `create_research_proposal` -> `execute_research` in CI/cron, exiting 0.
  - **Tier 1b (Hybrid Server)**: FastAPI server with `GET /health` and `POST /sessions/{id}/messages` providing SSE progress streams.
  - **Tier 2 (Modal Serverless)**: `modal.Sandbox.create` scale-to-zero container deployment with encrypted tunnels and volume mounts.
  - **Tier 3 (Kubernetes)**: Multi-tenant production gateway with isolated per-session pods and NetworkPolicy egress lockdown.
* **Slack Bot Gateway**:
  - `slack_app_manifest.yaml` configuring Socket Mode (WebSocket, no public HTTP listener required).
  - Handles `/research <query>` and channel `@researcher` mentions with threaded real-time progress updates.

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
| **Slack Bot Adapter** | `breakdown/services/slack_bot.py` | Slack Bolt Socket Mode handler for `/research` |
| **FastAPI Service** | `breakdown/services/server.py` | Tier 1b HTTP / SSE streaming endpoints |
| **Modal Sandbox** | `scripts/modal_researcher.py` | Tier 2 serverless deployment definition |
| **Slack Manifest** | `slack_app_manifest.yaml` | Declarative Slack app configuration |

---

## 5. Execution & Rollout Roadmap

1. **Step 1: Data Models & Contracts**:
   - Add `BaselineMap` and `NormalizedEvidence` to `breakdown/models.py`.
   - Update `ResearchExecutionOutput` to carry `baseline_map` and pre-normalized evidence.
2. **Step 2: Semantic Search Tool Integration**:
   - Implement `breakdown/tools/semantic_search.py` using Databricks Vector Search SDK with graceful offline fallback.
   - Register tool in `ROLE_TOOL_ALLOWLIST["researcher"]`.
3. **Step 3: Researcher Autonomous Engine & Subagents**:
   - Implement autonomous tool loop and Hub subagent delegation in `breakdown/roles/researcher.py`.
   - Validate delegation limits (max 3 workers, 3 rounds, read-only).
4. **Step 4: Auditor Review Refinement**:
   - Update `Auditor.review_research_findings` to act as the independent verification gate for Researcher-emitted findings.
5. **Step 5: Hosting Adapters & Slack Integration**:
   - Implement `breakdown/services/server.py` (FastAPI / SSE) and `slack_app_manifest.yaml`.
6. **Step 6: Comprehensive Test Suite & Gate Verification**:
   - Add unit tests in `tests/test_roles.py` and `tests/test_tools.py`.
   - Re-verify Phase 1-3 gates: `pytest`, `ruff check`, `mypy strict`, and `python evals/run.py --offline`.
