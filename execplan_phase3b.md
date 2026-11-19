# Phase 3b: Independent Verification, Cross-Run Memory, and Live Transport Retry


This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

The repository maintains `PLANS.md` at the repository root (`D:\Breakdown-tmp\PLANS.md`), the milestone and decision record for this project. This document must be maintained in accordance with PLANS.md: every decision recorded here that changes project behavior must also be appended to PLANS.md as a numbered decision entry (the next free numbers are D35 onward) during the documentation milestone.


## Purpose / Big Picture


Today every run of the OneShot Breakdown engine starts with a blank slate, and the engine authorizes writing built files into the target repository based on the builder role's own claim that its tasks succeeded — the implementer grades itself. After this change, three things become true, all visible from the command line without any Anthropic service.

First, an independent verifier — a separate model invocation with a fresh context that never sees the builder's reasoning — grades each built task against the plan's declared validation steps by reading the actual files in the build sandbox, and synchronization is authorized only when that independent grading passes. You see it working by running a scripted end-to-end scenario in tests where the builder claims success but the verifier reports failure, and observing that the run ends `failed` with no files synchronized.

Second, runs leave durable memory behind. When a run finishes (successfully or not), the engine writes a small markdown lesson document into a versioned memory store under the target's `.breakdown` state directory. Roles can read past lessons through three new canonical tools (`memory_list`, `memory_read`, `memory_search`), and a human can inspect them with `python -m breakdown memory list` and `memory show`. A live-only `consolidate-memory` command merges accumulated lessons into a fresh revision without ever modifying the inputs.

Third, live OpenAI-compatible backends survive transient rate limiting: 429, overloaded, and connection errors are retried with exponential backoff (honoring `Retry-After`) up to three times before the engine's existing stage-recovery takes over.

All of this is built on the project's own stores and the already-present `openai` Python package used purely as an HTTP client. No Anthropic API or SDK is introduced, and `breakdown.yaml` (the workflow definition) is not edited.


## Progress


- [x] (2026-11-18) Save this ExecPlan to `D:\Breakdown-tmp\execplan_phase3b.md` (file content is this document without the outer fence); confirm working tree clean at commit `d94208b`.
- [ ] Milestone 1: live transport retry in `breakdown/live_backend.py` plus `tests/test_live_retry.py`.
- [ ] Milestone 2: memory store models in `breakdown/models.py`, `breakdown/memory.py`, plus `tests/test_memory.py` (store layer only).
- [ ] Milestone 3: memory tools in `breakdown/tools.py`, `RoleToolkit.memory_root` wiring, allowlists, live-backend passthrough, plus tool-level tests.
- [ ] Milestone 4: deterministic lesson extraction in `breakdown/engine.py` `_complete_run`, `EngineStores.memory` field, bootstrap wiring, CLI `memory list|show`, plus tests.
- [ ] Milestone 5: independent verification — models, `breakdown/verification.py`, engine `_post_build` gate, verifier entry in role factories, demo scripted output, plus `tests/test_verification.py`.
- [ ] Milestone 6: CLI `consolidate-memory --live` command plus offline-refusal test.
- [ ] Milestone 7: docs (README, `.env.example`, PLANS.md D35–D38), full gate (pytest, ruff, ruff format, mypy, `--check`, offline evals), single git commit.




## Surprises & Discoveries


Findings from the pre-implementation gap review, verified against the source at `d94208b`. Keep adding entries as implementation reveals more.

- Observation: `build_execution` in `breakdown.yaml` declares no `runtime_steps` list (only `implementation_planning` declares `freeze_plan`/`preflight_check`), so adding an engine-side verification step creates no definition drift and needs no yaml edit.
  Evidence: yaml lines around the `build_execution` block show `synchronization:` with `requires:` entries but no `runtime_steps:` key.

- Observation: `_post_build` in `breakdown/engine.py` is called outside any try/except inside `_run_role_stage` (line ~465), and `advance()` does not wrap it either. Today it is purely deterministic, so nothing can raise; introducing a backend call there creates a new crash path that would exit the CLI without a terminal event.
  Evidence: code path `advance -> _run_role_stage -> _post_build` has no exception handling around `_post_build`; failures are only routed via its string return value into `_handle_stage_failure`.

- Observation: `_post_build(run_id, produced, approved_checkpoint)` has no sandbox parameter, but the sandbox path is in scope at its single call site, and `_post_build` itself loads the plan and build output from the artifact store — so verification belongs inside `_post_build` after those loads, with the sandbox passed in.
  Evidence: engine.py line 465 call site and `_post_build` body loading `BuildExecutionOutput` and `ImplementationPlan` via `self.stores.artifacts.get_model`.

- Observation: scripted backends (demo and test harnesses) key their canned outputs by `request.operation`, so adding a new operation string `verify_build_task` requires only a new dictionary entry — no protocol change.
  Evidence: `breakdown/demo.py` `OfflineDemoRoleBackend.generate` does `self._outputs.get(request.operation)`; `tests/test_engine_lifecycle.py` `ScriptedRoleBackend` works the same way.

- Observation: `EngineStores` and `RoleToolkit` are frozen slotted dataclasses; adding fields with defaults keeps every existing construction site compiling, which preserves backward compatibility for eval fakes and existing test harnesses.
  Evidence: `@dataclass(frozen=True, slots=True)` above `class EngineStores` in engine.py; `RoleToolkit` in `breakdown/roles/__init__.py` has fields `role: str` and `root: Path`.




## Decision Log


- Decision: Independent verification gates synchronization authorization (strong form): when a verifier backend is available, `integration_valid` inside `_post_build` is computed from the verifier's per-criterion results, not from the builder's self-reported `validation_results`. The builder's self-report remains stored as evidence.
  Rationale: This mirrors the reference "outcomes/grader" pattern where the grader uses a separate context window so it cannot be influenced by the implementer, and it closes a real soundness gap: today the party requesting synchronization authorization grades itself. Advisory-only verification would leave the gap open.
  Date/Author: 2026-11-18, planning agent.

- Decision: If the verifier backend raises or returns unusable output, verification produces `not_valid` CheckResult entries ("independent verifier unavailable") and synchronization is blocked; the run fails through the normal `_handle_stage_failure` path.
  Rationale: Authorization must be evidence-backed; absence of verification evidence is not evidence of validity. This also neutralizes the new exception path discovered in the gap review (no try/except around `_post_build`).
  Date/Author: 2026-11-18, planning agent.

- Decision: Factories that provide no `"verifier"` entry keep the legacy behavior (builder self-report gates sync).
  Rationale: Backward compatibility for eval fakes and existing engine test harnesses, which then double as regression coverage for the fallback path. The production bootstrap always supplies a verifier.
  Date/Author: 2026-11-18, planning agent.

- Decision: Memory writes are runtime-only. Roles receive read-only memory tools; the builder receives none. Lesson documents are written deterministically by the engine at run completion; consolidation writes a new revision through an explicit CLI command.
  Rationale: Model-driven memory writes would need their own containment and approval discipline and risk unbounded or strategic growth. Runtime-only writes keep memory an audit-grade record. This is recorded as project decision D36.
  Date/Author: 2026-11-18, planning agent.

- Decision: Memory revisions are append-only and immutable; consolidation output is written as a new revision (or new path) and never mutates existing content.
  Rationale: This reproduces the two reference properties we value — immutable versions as audit trail, and "the input store is never modified" from the consolidation/dream pattern — with no extra machinery.
  Date/Author: 2026-11-18, planning agent.


- Decision: `consolidate-memory` requires `--live` and validated bindings; offline invocation exits with a clear refusal. It builds its own client via the existing `build_openai_client`/`resolve_model` helpers with the verifier model tier and does not take the run lock.
  Rationale: Consolidation needs judgment (merging, deduplication, conflict resolution), which deterministic code cannot fake honestly; and it does not mutate run state, so the run lock is unnecessary. Recorded as D37.
  Date/Author: 2026-11-18, planning agent.

- Decision: Live transport retry covers `openai.RateLimitError`, `openai.APIConnectionError`, and `openai.APIStatusError` with status >= 500 or overload/rate-limit markers; up to 3 retries; exponential backoff from an injectable `retry_base_delay` (default 0.5s); `Retry-After` header honored when present. Applies to both role generation and coding `apply_task` calls through one shared wrapper. Recorded as D38.
  Rationale: Mirrors the reference workflow-runs guidance (retrying vs exhausted status) and prevents one transient 429 from consuming a whole stage attempt. Injectable delay keeps tests fast and deterministic.
  Date/Author: 2026-11-18, planning agent.

- Decision: Verification prompt assembly and response parsing live in a new module `breakdown/verification.py`; the engine only orchestrates the backend call. Sandbox file contents for each task's target paths are embedded in the verification input (size-capped per file), and no tools are granted to the verifier.
  Rationale: Keeps the engine thin, makes the grader's inputs inspectable/testable, and embedding files (instead of granting tool access) guarantees the verifier context contains only the rubric and observed state — never the builder's observations. Recorded as D35.
  Date/Author: 2026-11-18, planning agent.

- Decision: `breakdown.yaml` is not edited in this cycle; run-report memory citations are deferred.
  Rationale: The `synchronization.requires` entry `integration_validation_valid` keeps its declared name while its source of truth upgrades — pinning that meaning change belongs in PLANS.md, not the definition. Report citations would widen scope without closing any gap.
  Date/Author: 2026-11-18, planning agent.


## Outcomes & Retrospective


To be written at milestone boundaries and at completion. Compare results against the Purpose: does a verifier rejection demonstrably block synchronization, do completed runs leave readable lesson documents, do retried 429s no longer kill a stage, and does the full gate stay green.




## Context and Orientation


The project is a self-contained, contract-driven 8-stage workflow engine for one-shot code changes, living at `D:\Breakdown-tmp\`. A "run" walks a definition (`breakdown.yaml`, 8 stages from audit to completion) by activating one "role" per stage (auditor, researcher, planner, builder, plus a coder sub-role used by the auditor). Roles are Python classes in `breakdown/roles/` that produce strictly-typed pydantic models from `breakdown/models.py`. The engine (`breakdown/engine.py`, class `WorkflowEngine`) owns all progression; roles never call each other.

Backends execute role operations. A "backend" is an object with an async `generate(request)` method returning structured output. Two kinds exist: scripted/offline fakes (in `breakdown/demo.py` and inside test files) that return canned dictionaries keyed by `request.operation`, and live backends (`breakdown/live_backend.py`) that call any OpenAI-compatible HTTP endpoint through the `openai` Python package — used purely as an HTTP client; no OpenAI or Anthropic service is required. `breakdown/bootstrap.py` builds the runtime, wires backends per role, and enforces a lockfile so one process owns a target at a time.

Durability: `breakdown/artifact_store.py` is a content-addressed SQLite store for typed artifacts; `breakdown/events.py` is an append-only SQLite event log; `breakdown/run_store.py` persists run state; `breakdown/checkpoint.py` captures source checkpoints; `breakdown/safety.py` holds the `SafetyBoundary` (sandbox creation, changed-path detection, synchronization authorization); `breakdown/approvals.py` holds durable human decisions; `breakdown/completion.py` and `breakdown/reports.py` produce the terminal record and markdown reports. All state lives under the target repository's `.breakdown/` directory (the "state root").

The build stage deserves special attention. `_run_role_stage` in engine.py activates the builder, then — for `build_execution` only — calls `_post_build(run_id, produced, approved_checkpoint)`, which performs the synchronization sequence: detect changed paths in the sandbox, authorize via `SafetyBoundary.authorize_synchronization`, copy files into the target, reconcile. Today the authorization input `integration_valid` is derived from `BuildExecutionOutput.validation_results` — values the builder itself reported. That self-grading is the central defect this plan closes.

Key terms used below. "Sandbox": a temporary copy of the target repository where the builder applies tasks, created by `SafetyBoundary`. "Rubric": the per-task `validation_steps` and `expected_result` strings already declared in the frozen `ImplementationPlan` — the criteria a verifier grades against. "Verifier": a backend invocation in a fresh context that receives only the rubric and the actual sandbox file contents and returns per-criterion verdicts. "Memory store": a SQLite-backed collection of path-addressed markdown documents with append-only revisions, new in this plan. "Lesson document": a markdown file the engine writes to the memory store when a run reaches a terminal state.




## Plan of Work


The work proceeds in seven milestones, smallest and most isolated first, so each can be validated and committed mentally before the next begins; the git commit itself happens once at the end after the full gate.

Milestone 1 adds transport retry to `breakdown/live_backend.py`. A single private async helper wraps coroutine factories and retries transient errors; both the role backend's `generate` path and the coding backend's `apply_task` path route through it. A constructor parameter `retry_base_delay` makes backoff injectable for tests. New tests use the SDK's `MockTransport` to return 429 twice then 200, and to return 429 forever, asserting success-after-retry and bounded failure respectively.

Milestone 2 creates the memory store. New pydantic models `MemoryDocument` and `MemorySummary` go into `breakdown/models.py` (the project keeps all typed models there). A new module `breakdown/memory.py` implements `MemoryStore` over a SQLite database file `memory.db` in the state root: two tables, `memories` (latest revision per path) and `memory_versions` (every revision, immutable). Writes append a version row and update the head row; reads resolve a path to its head or a pinned revision; list filters by path prefix; search applies a Python regex over the content of head revisions. A private path-validation helper rejects empty paths, absolute paths, backslashes, and `..` segments, normalizing to forward slashes.

Milestone 3 exposes memory to roles as read-only canonical tools. `breakdown/tools.py` gains request models and three `CanonicalTool` entries (`memory_list`, `memory_read`, `memory_search`) flagged with a new `needs_memory_root` boolean; `dispatch_tool` gains a keyword-only `memory_root` parameter and raises `ToolNotAuthorized("memory store not configured")` when a memory tool is called without one. `ROLE_TOOL_ALLOWLIST` grants the three tools to auditor, researcher, coder, and planner; the builder keeps its empty tuple. `RoleToolkit` in `breakdown/roles/__init__.py` gains `memory_root: Path | None = None` and passes it through `call`. `OpenAICompatibleRoleBackend` gains the same parameter for its tool dispatch. Role brief constants for the four reading roles gain one sentence telling them to consult memory for prior lessons.

Milestone 4 wires memory into run lifecycle. `EngineStores` gains `memory: MemoryStore | None = None`. `_complete_run` in engine.py, after building the completion record, writes one lesson document when a memory store is present: for failed or cancelled runs, `lessons/<run_id>.md` containing terminal outcome, reason, failed stage, attempt counts, and cost totals; for successful runs, `runs/<run_id>.md` containing the objective, stage sequence, and cost. Content is deterministic markdown built from data already in the run record and completion record — no model calls. `bootstrap.build_runtime` constructs the `MemoryStore` and passes it into `EngineStores` and as `memory_root` into toolkits. The CLI gains a `memory` subcommand with `list [--prefix P]` and `show PATH [--revision N]` actions; these open the store read-only and take no lock.

Tooling conventions. Work from `D:\Breakdown-tmp\` in PowerShell. The environment uses `uv`; run everything through `uv run --no-sync`. Pytest must be given `--basetemp=.pytest-tmp` because the system temp directory denies pytest's default base temp (the pyproject already carries addopts, but pass it explicitly if running subset commands). The full gate is: pytest, ruff check, ruff format check, mypy over `breakdown evals scripts tests`, `python -m breakdown --check`, and `python evals/run.py --offline`. Current baseline: 255 tests passing, evals 16/16, working tree clean at commit `d94208b`.

Milestone 5 implements independent verification. `breakdown/models.py` gains `ObservedFile`, `VerificationTaskView`, `BuildVerificationInput`, and `BuildVerificationOutput` (the last holding `task_verifications: tuple[CheckResult, ...]`, reusing the existing `CheckResult` model with fields `check_ref`, `criterion`, `expected`, `actual_observation`). `Settings` gains `model_verifier: str | None`. A new module `breakdown/verification.py` provides pure functions: one assembles `BuildVerificationInput` from the frozen plan, the build output, and the sandbox (reading each task's target files, capping each embedded file at 8000 characters with a truncation flag); one wraps that input in a `RoleBackendRequest` with operation `verify_build_task`, empty tool list, and `BuildVerificationOutput` as output model; one parses the response into `CheckResult` tuples and maps any `uncertainty` verdict to blocking (the definition's `stop_on_criterion` already lists `uncertainty`). `_post_build` gains a `sandbox` parameter; after loading plan and build output it looks up `self._role_factory(None).get("verifier")`; if present it runs verification inside a try/except where any exception yields blocking `not_valid` results citing verifier unavailability, stores the results as artifact `independent_verification`, attributes the verifier's `response.usage` to the build stage via the existing `_add_stage_usage`, and computes `integration_valid` from the independent results; if absent it keeps today's self-report path unchanged. `demo_role_outputs` in `breakdown/demo.py` gains a `verify_build_task` entry with all-valid criteria. `bootstrap.build_live_backends` and both role factories gain a `"verifier"` entry: an `OpenAICompatibleRoleBackend` (or scripted equivalent in tests) resolved through `resolve_model(settings, "verifier")`, which falls back to `settings.model` when `model_verifier` is unset.

Milestone 6 adds the consolidation command. `consolidate-memory --live [--instructions TEXT]` validates bindings the same way `_build_live_runtime` does, builds a client via `build_openai_client`, constructs one backend call with operation `consolidate_memory` whose input embeds every `lessons/*` document, the current `consolidated/lessons.md` if present, and the optional instructions, and whose output model `ConsolidationOutput` (new in models.py: `consolidated: str`, `changes_summary: str`) is written as a new memory revision at `consolidated/lessons.md` with `run_id=None`. Without `--live` the command prints a refusal explaining consolidation requires a live model and exits nonzero.

Milestone 7 documents and gates. README gains short sections on independent verification and memory. `.env.example` gains `BREAKDOWN_MODEL_VERIFIER`. PLANS.md gains decision entries D35–D38 and a short equivalence note recording that session-thread and workflow-run inspection patterns are already covered by the event log, per-stage attribution, resume, and cancel. The full gate runs; then one commit.





## Concrete Steps


All commands run from working directory `D:\Breakdown-tmp\` in PowerShell. After each milestone, run the focused test file first, then the fast static checks, before moving on.

Baseline check (before any edit):

    uv run --no-sync pytest -q --basetemp=.pytest-tmp
    git status --short

Expected: `255 passed` and empty git status output.

Milestone 1 tests:

    uv run --no-sync pytest -q --basetemp=.pytest-tmp tests/test_live_retry.py

Expected after implementation: 3 passed. Before the retry wrapper exists, these tests fail with un-retried `RateLimitError` — that red-then-green sequence is the proof of behavior.

Milestones 2–4 tests:

    uv run --no-sync pytest -q --basetemp=.pytest-tmp tests/test_memory.py
    uv run --no-sync pytest -q --basetemp=.pytest-tmp tests/test_engine_lifecycle.py

Milestone 5 tests:

    uv run --no-sync pytest -q --basetemp=.pytest-tmp tests/test_verification.py

Manual end-to-end observation of memory after milestone 4, using the offline demo against a scratch target (create a temp git repo with one file first):

    uv run --no-sync python -m breakdown run --target <scratch> --request "demo task" --offline-demo
    uv run --no-sync python -m breakdown memory list --target <scratch>
    uv run --no-sync python -m breakdown memory show runs/<run_id>.md --target <scratch>

Expected: the run completes, `memory list` shows one `runs/<run_id>.md` entry at revision 1, and `memory show` prints the deterministic lesson markdown.

Full gate before commit (milestone 7):

    uv run --no-sync pytest -q --basetemp=.pytest-tmp
    uv run --no-sync ruff check .
    uv run --no-sync ruff format --check .
    uv run --no-sync mypy breakdown evals scripts tests
    uv run --no-sync python -m breakdown --check
    uv run --no-sync python evals/run.py --offline

Expected: roughly 271–275 passed (255 baseline plus the new rows), ruff and format silent, mypy `Success: no issues found`, `--check` printing the definition-consistency confirmation, evals reporting 16/16 with zero blocking failures.

Commit:

    git add -A
    git commit -m "Phase 3b: independent verification, cross-run memory, live transport retry (D35-D38)"


## Validation and Acceptance


Acceptance is behavioral. A human can verify each claim without reading the implementation.

Verifier rejection blocks synchronization: in `tests/test_verification.py`, a lifecycle scenario scripts the builder to report all tasks valid and scripts the verifier to return `not_valid` for one criterion. Running the suite shows the run reaching terminal state `failed` with a reason naming independent verification, and the scenario asserts the target repository contains none of the sandbox-produced files. This test fails (sync proceeds) if the gate is removed — it is the regression anchor for D35.

Verifier absence preserves legacy behavior: existing lifecycle rows, whose factories provide no `"verifier"` key, still pass unchanged, proving backward compatibility.

Verifier failure is conservative: a row where the verifier backend raises yields terminal `failed` with "independent verifier unavailable" recorded, never a crash and never an authorization.

Memory persists and is inspectable: after the offline demo run shown in Concrete Steps, `memory list` and `memory show` print the lesson document; a second failed demo run adds a `lessons/<run_id>.md` entry at revision 1; rewriting the same path (only possible through the store API in tests) creates revision 2 while `memory show PATH --revision 1` still returns the original content — proving immutable versions.

Memory is contained: `tests/test_memory.py` rows show the builder's allowlist excludes memory tools, `memory_read` with `../` or absolute paths raises, and a `RoleToolkit` without `memory_root` raises `ToolNotAuthorized("memory store not configured")`.

Retry works: `tests/test_live_retry.py` shows a mock transport returning 429 twice then 200 producing a successful generation with exactly three requests observed, a permanent 429 raising `LiveBackendError` after four total attempts (initial plus three retries), and a `Retry-After: 0` header being honored without real sleeping (base delay injected as 0.0).




## Idempotence and Recovery


Every step is additive and re-runnable. The memory store opens its SQLite database with create-if-missing semantics, so running any command twice causes no drift; lesson paths are keyed by run id, so repeated runs add distinct documents rather than overwriting. If a milestone's tests fail halfway, re-run the focused test file after fixing; nothing in this plan mutates existing stored formats, so there is no migration to roll back. The only destructive-adjacent operation is the final `git add -A && git commit`; if the gate fails after staging, `git reset` restores the pre-commit state while keeping the working files. The scratch target used for manual observation is disposable; delete it afterwards and leave `.pytest-tmp` as the only local artifact, consistent with existing project hygiene.


## Artifacts and Notes


Expected shape of a lesson document written by milestone 4 (deterministic markdown, values from the run record):

    # Run lesson: run-20261118-0001

    - Terminal outcome: failed
    - Reason: build task returned not_valid
    - Failed stage: build_execution (attempt 2)
    - Tokens used: 18234; tool calls: 41
    - Cost by stage: build_execution=0.0312 USD

Expected transcript for the manual memory observation (abridged):

    $ uv run --no-sync python -m breakdown memory list --target scratch
    path                     revision  created
    runs/run-20261118-0001.md        1  2026-11-18T...

The verification artifact stored under key `independent_verification` is the `BuildVerificationOutput` model; inspect it in tests via `stores.artifacts.get_model` to assert per-criterion verdicts.



## Interfaces and Dependencies


Dependencies: Python 3.12, `pydantic` v2 (already used project-wide via the `StrictModel` base in `breakdown/models.py`), the standard library `sqlite3` and `re`, and `openai>=1.50,<3` (already pinned; used only for its HTTP client and its exception types `RateLimitError`, `APIConnectionError`, `APIStatusError`, plus `MockTransport` from `httpx` in tests, which openai already depends on). No new packages are added.

In `breakdown/models.py`, define:

    class MemorySummary(StrictModel):
        path: str = Field(min_length=1)
        revision: int = Field(ge=1)
        digest: str = Field(min_length=1)
        created_at: datetime

    class MemoryDocument(MemorySummary):
        content: str
        run_id: str | None = None

    class ObservedFile(StrictModel):
        path: str = Field(min_length=1)
        content: str
        truncated: bool = False

    class VerificationTaskView(StrictModel):
        task_ref: str = Field(min_length=1)
        description: str
        expected_result: str
        validation_steps: tuple[str, ...]
        observed_files: tuple[ObservedFile, ...]

    class BuildVerificationInput(StrictModel):
        run_id: str
        tasks: tuple[VerificationTaskView, ...] = Field(min_length=1)

    class BuildVerificationOutput(StrictModel):
        task_verifications: tuple[CheckResult, ...] = Field(min_length=0)

    class ConsolidationOutput(StrictModel):
        consolidated: str = Field(min_length=1)
        changes_summary: str

Add to `Settings`: `model_verifier: str | None = None`.

In `breakdown/memory.py`, define:

    class MemoryStore:
        def __init__(self, root: Path) -> None: ...
        def write(self, path: str, content: str, *, run_id: str | None = None) -> int: ...
        def read(self, path: str, revision: int | None = None) -> MemoryDocument | None: ...
        def list(self, prefix: str = "") -> tuple[MemorySummary, ...]: ...
        def search(self, pattern: str) -> tuple[MemorySummary, ...]: ...

`write` returns the new revision number (1 for a new path, previous+1 otherwise) and computes `digest` with the project's canonical digest helper from `breakdown/canonical.py`. `read` with `revision=None` returns the head revision. `search` matches a Python regular expression against head-revision content and returns summaries ordered by path.

In `breakdown/verification.py`, define:

    def build_verification_input(run_id: str, plan: ImplementationPlan, build_output: BuildExecutionOutput, sandbox: Path, *, max_file_chars: int = 8000) -> BuildVerificationInput: ...
    def verification_request(input_: BuildVerificationInput) -> RoleBackendRequest: ...
    def parse_verification(response: RoleBackendResponse, input_: BuildVerificationInput) -> tuple[CheckResult, ...]: ...
    def verification_failure_reason(results: tuple[CheckResult, ...]) -> str | None: ...

`verification_request` sets `operation="verify_build_task"`, `tool_names=()`, and `output_model=BuildVerificationOutput`. `verification_failure_reason` returns None only when every criterion is `valid`; `uncertainty` and `not_valid` both block, with the returned string naming the offending task refs and criteria.

In `breakdown/tools.py`, extend:

    @dataclass(frozen=True, slots=True)
    class CanonicalTool:
        ...
        needs_memory_root: bool = False

    def dispatch_tool(name: str, payload: Mapping[str, Any], *, root: Path, memory_root: Path | None = None) -> Any: ...

In `breakdown/roles/__init__.py`, extend `RoleToolkit` with `memory_root: Path | None = None` and pass it into `dispatch_tool`. In `breakdown/live_backend.py`, extend `OpenAICompatibleRoleBackend.__init__` with `memory_root: Path | None = None` and `retry_base_delay: float = 0.5`, and add the shared retry helper used by both backend classes. In `breakdown/engine.py`, extend `EngineStores` with `memory: MemoryStore | None = None` and change the `_post_build` signature to `_post_build(self, run_id, produced, approved_checkpoint, sandbox: Path)`. Role factories in `breakdown/bootstrap.py` and in test harnesses may include the key `"verifier"` mapping to any object satisfying the `RoleBackend` protocol (async `generate(request) -> RoleBackendResponse`); its presence opts the run into independent verification.


## Revision Notes


- 2026-11-18: Initial ExecPlan authored from the Phase 3b gap-reviewed plan. All sections written at once from verified source inspection at commit `d94208b`; the gap-review findings (G1–G14 from the planning discussion) are embedded in `Surprises & Discoveries` and `Decision Log` so no external context is needed to restart from this document alone.


Definition integrity: `python -m breakdown --check` passes unchanged, proving no yaml drift, and `git diff d94208b -- breakdown.yaml` is empty.
