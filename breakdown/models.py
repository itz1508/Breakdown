"""Authoritative typed contracts for OneShot Breakdown (Phase 1).

Every model rejects unknown fields (``extra="forbid"``), carries an explicit
``schema_version``, uses timezone-aware datetimes, and distinguishes artifact
references from embedded records. JSON records are authoritative; Markdown is
a derived readable view.

Vocabulary separation (never conflate):

- RunState: workflow run lifecycle.
- ExecutionStatus: stage / processing-plan lifecycle (definition vocabulary).
- ExecutionResult: task and check execution outcomes.
- CriterionResult: assessment criteria; ``uncertainty`` never advances.
- FindingStatus: evidence assessment for research findings.

Lifecycle ``failed`` is never substituted for criterion ``not_valid``.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SCHEMA_VERSION = "1"

# Paths that may never be build targets unless explicitly authorized.
PROTECTED_PATHS = frozenset(
    {
        ".env",
        ".git",
        ".breakdown",
        "agents",
        "breakdown.yaml",
        "AGENTS.md",
        "PLANS.md",
        "pyproject.toml",
        "uv.lock",
    }
)


def validate_target_path(raw: str) -> str:
    """Normalize a repository-relative target path or raise ValueError."""
    if not raw or raw.strip() != raw:
        raise ValueError("target path must be a non-empty, unpadded string")
    posix = PurePosixPath(raw.replace("\\", "/"))
    if posix.is_absolute() or ".." in posix.parts:
        raise ValueError(f"target path must be repository-relative without traversal: {raw}")
    normalized = posix.as_posix()
    head = normalized.split("/", 1)[0]
    if normalized in PROTECTED_PATHS or head in PROTECTED_PATHS:
        raise ValueError(f"target path is protected: {raw}")
    return normalized


class StrictModel(BaseModel):
    """Base for authoritative contracts: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION


class RunState(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    AWAITING_DECISION = "awaiting_decision"
    CANCELLING = "cancelling"
    TERMINAL = "terminal"


class ExecutionStatus(StrEnum):
    """Stage / processing-plan lifecycle (workflow definition vocabulary)."""

    NOT_RUN = "not_run"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ExecutionResult(StrEnum):
    """Task and check execution outcomes."""

    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NOT_RUN = "not_run"
    SKIPPED = "skipped"


class CriterionResult(StrEnum):
    """Assessment criteria. ``uncertainty`` never advances a stage or gate."""

    VALID = "valid"
    NOT_VALID = "not_valid"
    UNCERTAINTY = "uncertainty"


class FindingStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    CONTRADICTED = "contradicted"
    UNRESOLVED = "unresolved"


class CapabilityCoverage(StrEnum):
    COVERED = "covered"
    PARTIAL = "partial"
    NOT_COVERED = "not_covered"
    UNCERTAINTY = "uncertainty"


class ContractKind(StrEnum):
    ROLE = "role"
    DECISION = "decision"
    DETERMINISTIC = "deterministic"


class EventPersistence(StrEnum):
    PERSISTENT = "persistent"
    EPHEMERAL = "ephemeral"


class EventType(StrEnum):
    STAGE_ENTERED = "stage_entered"
    STAGE_COMPLETED = "stage_completed"
    STAGE_FAILED = "stage_failed"
    STAGE_CANCELLED = "stage_cancelled"
    ARTIFACT_PRODUCED = "artifact_produced"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RECORDED = "approval_recorded"
    COST_THRESHOLD_APPROACHED = "cost_threshold_approached"
    RUN_COMPLETED = "run_completed"
    ACTIVITY_UPDATED = "activity_updated"

    @property
    def persistence(self) -> EventPersistence:
        if self is EventType.ACTIVITY_UPDATED:
            return EventPersistence.EPHEMERAL
        return EventPersistence.PERSISTENT


class Settings(BaseSettings):
    """Runtime settings loaded from environment / .env.

    Secrets are never part of settings; a model backend authenticates
    through its own SDK environment convention.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="BREAKDOWN_", extra="ignore")

    workflow_path: Path = Path("breakdown.yaml")
    target_repo: Path = Path(".")
    state_root: Path = Path(".breakdown")
    backend_bindings_path: Path | None = None
    # Live OpenAI-compatible API (Databricks Model Serving, custom gateway,
    # or OpenAI). Secrets stay SecretStr: never logged, never persisted.
    api_base_url: str | None = None
    api_key: SecretStr | None = None
    model: str | None = None
    model_auditor: str | None = None
    model_researcher: str | None = None
    model_coder: str | None = None
    model_planner: str | None = None
    api_max_tool_rounds: int = Field(default=8, ge=1)


class InitialRequest(StrictModel):
    text: str = Field(min_length=1)
    created_at: AwareDatetime


class RunRef(StrictModel):
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    definition_version: int = Field(ge=1)
    definition_digest: str = Field(min_length=1)


class ArtifactRef(StrictModel):
    """Reference to a persisted artifact; never the bytes themselves."""

    artifact_key: str = Field(min_length=1)
    digest: str = Field(min_length=1)
    revision: int = Field(default=1, ge=1)


class ArtifactRevision(StrictModel):
    artifact_key: str = Field(min_length=1)
    revision: int = Field(ge=1)
    digest: str = Field(min_length=1)
    created_at: AwareDatetime


class StoredValue(StrictModel):
    """Envelope for scalar/tuple artifacts in the BaseModel-only store.

    Role mappers emit models, strings, and tuples; the artifact store
    persists models, so non-model values travel in this envelope and are
    unwrapped on input assembly.
    """

    value: Any


class SourceCheckpoint(StrictModel):
    repository_identity: str = Field(min_length=1)
    commit_sha: str | None = None
    file_hashes: Mapping[str, str] = Field(default_factory=dict)
    untracked_file_hashes: Mapping[str, str] = Field(default_factory=dict)
    captured_at: AwareDatetime

    @property
    def identity_inputs(self) -> tuple[str, ...]:
        tracked = tuple(f"{path}:{digest}" for path, digest in sorted(self.file_hashes.items()))
        untracked = tuple(f"{path}:{digest}" for path, digest in sorted(self.untracked_file_hashes.items()))
        return (self.repository_identity, self.commit_sha or "", *tracked, *untracked)


class StageContext(StrictModel):
    run: RunRef
    stage_id: str = Field(min_length=1)
    attempt: int = Field(default=1, ge=1)
    inputs: Mapping[str, ArtifactRef] = Field(default_factory=dict)


class StageResult(StrictModel):
    stage_id: str = Field(min_length=1)
    criterion: CriterionResult
    produces: Mapping[str, Any] = Field(default_factory=dict)
    reason: str = ""
    # Backend-reported usage for budget enforcement (runtime accumulates it).
    usage: TokenUsage | None = None

    @classmethod
    def valid(cls, stage_id: str, produces: Mapping[str, Any]) -> StageResult:
        return cls(stage_id=stage_id, criterion=CriterionResult.VALID, produces=produces)

    @classmethod
    def not_valid(cls, stage_id: str, reason: str) -> StageResult:
        return cls(stage_id=stage_id, criterion=CriterionResult.NOT_VALID, reason=reason)

    @classmethod
    def uncertainty(cls, stage_id: str, reason: str) -> StageResult:
        return cls(stage_id=stage_id, criterion=CriterionResult.UNCERTAINTY, reason=reason)


class ProcessingPlan(StrictModel):
    """One cross-role handoff plan.

    Authored fields are written by the producing role; ``execution_status``
    is a runtime field and is never authored by roles.
    """

    objective: str = Field(min_length=1)
    input_refs: tuple[str, ...] = Field(min_length=1)
    steps: tuple[str, ...] = Field(min_length=1)
    expected_output_keys: tuple[str, ...] = Field(min_length=1)
    completion_criteria: tuple[str, ...] = Field(min_length=1)
    evidence_required: tuple[str, ...] = Field(min_length=1)
    constraints: tuple[str, ...] = ()
    unresolved_items: tuple[str, ...] = ()
    execution_status: ExecutionStatus = ExecutionStatus.NOT_RUN


# --- Research proposal (Auditor.create_research_proposal) ---


class CandidateRequirement(StrictModel):
    requirement_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    origin: Literal["user", "inferred"]
    coverage: CapabilityCoverage
    evidence: str = Field(min_length=1)
    remaining_responsibility: str | None = None
    research_question_ref: str | None = None

    @model_validator(mode="after")
    def _coverage_rules(self) -> CandidateRequirement:
        if self.coverage is CapabilityCoverage.PARTIAL and not self.remaining_responsibility:
            raise ValueError("partial coverage must name the remaining responsibility")
        if self.coverage is CapabilityCoverage.NOT_COVERED and not self.evidence:
            raise ValueError("not_covered requires evidence-backed justification")
        if self.coverage is CapabilityCoverage.UNCERTAINTY and not self.research_question_ref:
            raise ValueError("uncertain coverage must map to a research question")
        return self


class ResearchQuestion(StrictModel):
    question_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class CandidateSourceResponsibility(StrictModel):
    """A proposed source responsibility; exact paths only when verified."""

    requirement_refs: tuple[str, ...] = Field(min_length=1)
    purpose: str = Field(min_length=1)
    path: str | None = None

    @model_validator(mode="after")
    def _path_rules(self) -> CandidateSourceResponsibility:
        if self.path is not None:
            validate_target_path(self.path)
        return self


class ResearchProposalInput(StrictModel):
    initial_request: InitialRequest


class ResearchProposalOutput(StrictModel):
    exact_user_intent: str = Field(min_length=1)
    candidate_requirements: tuple[CandidateRequirement, ...] = Field(min_length=1)
    research_questions: tuple[ResearchQuestion, ...] = ()
    candidate_source_responsibilities: tuple[CandidateSourceResponsibility, ...] = ()
    # Authored by the Auditor per breakdown.yaml creates_processing_plan
    # (destination: research_execution); activated by runtime on approval.
    research_execution_processing_plan: ProcessingPlan


# --- Research execution (Researcher.execute_research) ---


class ResearchTodoItem(StrictModel):
    question_id: str = Field(min_length=1)
    status: ExecutionStatus = ExecutionStatus.NOT_RUN
    note: str = ""


class ResearchTodo(StrictModel):
    items: tuple[ResearchTodoItem, ...] = Field(min_length=1)


class EvidenceRecord(StrictModel):
    evidence_id: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    source_identity: str = Field(min_length=1)
    source_location: str = Field(min_length=1)
    source_version: str | None = None
    accessed_at: AwareDatetime
    quoted_excerpt: str | None = None
    status: FindingStatus


class FixtureSpecification(StrictModel):
    fixture_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    known_properties: tuple[str, ...] = ()
    setup: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    expected_observations: tuple[str, ...] = ()
    evidence_to_capture: tuple[str, ...] = ()


class ResolvedQuestion(StrictModel):
    question_id: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class UnresolvedQuestion(StrictModel):
    question_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    missing_information: str = Field(min_length=1)


class Contradiction(StrictModel):
    topic: str = Field(min_length=1)
    positions: tuple[str, ...] = Field(min_length=2)
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class ResearchRecord(StrictModel):
    """Authoritative Research response schema."""

    record_id: str = Field(min_length=1)
    resolved_questions: tuple[ResolvedQuestion, ...] = ()
    unresolved_questions: tuple[UnresolvedQuestion, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()
    contradictions: tuple[Contradiction, ...] = ()
    fixture_specifications: tuple[FixtureSpecification, ...] = ()


class ResearchExecutionInput(StrictModel):
    research_proposal: ResearchProposalOutput
    processing_plan: ProcessingPlan
    research_approval_ref: ArtifactRef
    source_checkpoint: SourceCheckpoint


class ResearchExecutionOutput(StrictModel):
    research_record: ResearchRecord
    report_summary: str = Field(min_length=1)
    # Final snapshot of the question-tracking todo authored during execution.
    research_todo: ResearchTodo


# --- Findings review (Auditor.review_research_findings) ---


class DecisionTraceStep(StrictModel):
    check: str = Field(min_length=1)
    observation: Literal["true", "false", "unknown"]
    evidence_ref: str | None = None


class ClassifiedFinding(StrictModel):
    finding_id: str = Field(min_length=1)
    requirement_ref: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    status: FindingStatus
    decision_trace: tuple[DecisionTraceStep, ...] = Field(min_length=1)
    criterion: CriterionResult
    reason: str = Field(min_length=1)


class NormalizedEvidence(StrictModel):
    evidence_ref: str = Field(min_length=1)
    normalized_form: str = Field(min_length=1)
    provenance_preserved: Literal[True] = True


class FindingsReviewInput(StrictModel):
    research_record: ResearchRecord
    research_proposal: ResearchProposalOutput
    exact_user_intent: str = Field(min_length=1)
    source_checkpoint: SourceCheckpoint


class FindingsReviewOutput(StrictModel):
    classified_findings: tuple[ClassifiedFinding, ...] = Field(min_length=1)
    normalized_evidence: tuple[NormalizedEvidence, ...] = ()
    reviewed_fixture_specifications: tuple[FixtureSpecification, ...] = ()
    reviewed_unresolved_questions: tuple[UnresolvedQuestion, ...] = ()
    contradictions_preserved: tuple[Contradiction, ...] = ()
    # Authored by the Auditor per breakdown.yaml creates_processing_plan
    # (destination: implementation_planning); activated on stage completion.
    implementation_planning_processing_plan: ProcessingPlan


# --- Coder (read-only Auditor sub-role) ---


class CodeAnalysisRequest(StrictModel):
    question: str = Field(min_length=1)
    scope_paths: tuple[str, ...] = Field(min_length=1)
    context_refs: tuple[str, ...] = ()


class FileEvidence(StrictModel):
    path: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)


class CodeAnalysisEvidence(StrictModel):
    answer: str = Field(min_length=1)
    file_evidence: tuple[FileEvidence, ...] = Field(min_length=1)
    criterion: CriterionResult


# --- Implementation planning (Planner.create_implementation_plan) ---


class TargetPath(StrictModel):
    path: str = Field(min_length=1)
    disposition: Literal["create", "modify", "delete", "move"]

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        return validate_target_path(value)


class CheckDefinition(StrictModel):
    check_id: str = Field(min_length=1)
    kind: Literal["command", "observation"]
    check: str = Field(min_length=1)
    expected: str = ""


class CapabilityReuseDecision(StrictModel):
    capability: str = Field(min_length=1)
    coverage: CapabilityCoverage
    distribution_name: str | None = None
    import_name: str | None = None
    verified_version: str | None = None
    public_api: str | None = None
    evidence_refs: tuple[str, ...] = ()
    remaining_custom_responsibility: str | None = None
    custom_implementation_decision: str | None = None

    @model_validator(mode="after")
    def _coverage_rules(self) -> CapabilityReuseDecision:
        if self.coverage is CapabilityCoverage.COVERED and self.custom_implementation_decision:
            raise ValueError("covered capability must not be reimplemented")
        if self.coverage is CapabilityCoverage.PARTIAL and not self.remaining_custom_responsibility:
            raise ValueError("partial coverage must name only the remaining custom responsibility")
        if self.coverage is CapabilityCoverage.NOT_COVERED and not (
            self.evidence_refs and self.custom_implementation_decision
        ):
            raise ValueError("not_covered requires evidence and an explicit custom implementation decision")
        return self


class TechnologyDecision(StrictModel):
    topic: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = ()


class ValidationStep(StrictModel):
    step_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    command_or_observation: str = Field(min_length=1)
    expected: str = Field(min_length=1)


class BuildTask(StrictModel):
    """One cohesive, independently verifiable change with >=1 approved target paths."""

    task_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    responsibility: str = Field(min_length=1)
    requirement_refs: tuple[str, ...] = Field(min_length=1)
    target_paths: tuple[TargetPath, ...] = Field(min_length=1)
    source_evidence: tuple[str, ...] = ()
    capability_reuse: tuple[CapabilityReuseDecision, ...] = ()
    reference_ids: tuple[str, ...] = ()
    expected_result: str = Field(min_length=1)
    validation_steps: tuple[ValidationStep, ...] = Field(min_length=1)
    required_evidence: tuple[str, ...] = Field(min_length=1)
    depends_on: tuple[str, ...] = ()


class SuccessCriterion(StrictModel):
    criterion: str = Field(min_length=1)
    measurable: bool = True


class ImplementationPlan(StrictModel):
    """The single authoritative Planning output."""

    plan_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    objective: str = Field(min_length=1)
    requirement_refs: tuple[str, ...] = Field(min_length=1)
    source_checkpoint_ref: ArtifactRef
    technology_decisions: tuple[TechnologyDecision, ...] = ()
    tasks: tuple[BuildTask, ...] = Field(min_length=1)
    integration_checks: tuple[CheckDefinition, ...] = ()
    success_criteria: tuple[SuccessCriterion, ...] = Field(min_length=1)
    fixture_refs: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    unresolved_items: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _task_rules(self) -> ImplementationPlan:
        ids = [task.task_id for task in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("task_ids must be unique")
        sequences = sorted(task.sequence for task in self.tasks)
        if sequences != list(range(1, len(sequences) + 1)):
            raise ValueError("task sequence must start at 1 and be contiguous")
        by_id = {task.task_id: task for task in self.tasks}
        owners: dict[str, str] = {}
        for task in self.tasks:
            for target in task.target_paths:
                owner_id = owners.get(target.path)
                if owner_id is not None and owner_id != task.task_id:
                    owner_task = by_id[owner_id]
                    if owner_id not in task.depends_on and task.task_id not in owner_task.depends_on:
                        raise ValueError(
                            f"target path {target.path} belongs to multiple tasks without an explicit dependency"
                        )
                owners.setdefault(target.path, task.task_id)
        return self


class PlanningReviewResult(StrictModel):
    cohesion: CriterionResult
    notes: str = ""


class ImplementationPlanningInput(StrictModel):
    processing_plan: ProcessingPlan
    classified_findings: tuple[ClassifiedFinding, ...] = Field(min_length=1)
    normalized_evidence: tuple[NormalizedEvidence, ...] = ()
    reviewed_fixture_specifications: tuple[FixtureSpecification, ...] = ()
    reviewed_unresolved_questions: tuple[UnresolvedQuestion, ...] = ()
    exact_user_intent: str = Field(min_length=1)
    source_checkpoint: SourceCheckpoint


class ImplementationPlanningOutput(StrictModel):
    planning_gap_analysis: tuple[str, ...] = ()
    planning_gap_resolutions: tuple[str, ...] = ()
    implementation_plan: ImplementationPlan
    planning_review_result: PlanningReviewResult
    # Authored by the Planner per breakdown.yaml creates_processing_plan
    # (destination: build_execution); runtime activates it only when
    # preflight_result.criterion_result == valid and plan approval lands.
    build_execution_processing_plan: ProcessingPlan


class FrozenPlan(StrictModel):
    plan: ImplementationPlan
    frozen_plan_hash: str = Field(min_length=1)
    source_checkpoint: SourceCheckpoint
    definition_version: int = Field(ge=1)
    frozen_at: AwareDatetime


class PreflightCriterionRow(StrictModel):
    name: str = Field(min_length=1)
    criterion: CriterionResult
    evidence: str = ""


class PreflightResult(StrictModel):
    criterion: CriterionResult
    criteria_results: tuple[PreflightCriterionRow, ...] = Field(min_length=1)
    checked_at: AwareDatetime


# --- Build execution (Builder.execute_build) ---


class TaskResult(StrictModel):
    task_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    criterion: CriterionResult
    execution_result: ExecutionResult
    expected: str = Field(min_length=1)
    actual_observation: str = Field(min_length=1)
    attempts: int = Field(default=1, ge=1)
    evidence_refs: tuple[str, ...] = ()


class CheckResult(StrictModel):
    check_ref: str = Field(min_length=1)
    criterion: CriterionResult
    expected: str = ""
    actual_observation: str = ""


class SynchronizationResult(StrictModel):
    authorized: bool
    authorized_by: Literal["runtime"] = "runtime"
    copied_paths: tuple[str, ...] = ()
    blocked_reason: str | None = None

    @model_validator(mode="after")
    def _authorization_rules(self) -> SynchronizationResult:
        if self.authorized and self.blocked_reason:
            raise ValueError("authorized synchronization cannot carry a blocked reason")
        if not self.authorized and not self.blocked_reason:
            raise ValueError("blocked synchronization must record a reason")
        return self


class ImportedCapability(StrictModel):
    capability: str = Field(min_length=1)
    source: str = Field(min_length=1)
    version: str | None = None


class BuildExecutionInput(StrictModel):
    implementation_plan: ImplementationPlan
    frozen_plan_hash: str = Field(min_length=1)
    preflight_result: PreflightResult
    plan_approval_ref: ArtifactRef
    approval_hash: str = Field(min_length=1)
    approved_plan_revision: int = Field(ge=1)
    approved_source_checkpoint: SourceCheckpoint
    processing_plan: ProcessingPlan
    # build_execution.stop_on_criterion from the definition (empty = role default)
    stop_on_criterion: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _preflight_must_be_valid(self) -> BuildExecutionInput:
        if self.preflight_result.criterion is not CriterionResult.VALID:
            raise ValueError("build execution requires a valid preflight result")
        return self


class BuildExecutionOutput(StrictModel):
    task_results: tuple[TaskResult, ...] = Field(min_length=1)
    applied_changes: tuple[str, ...] = ()
    validation_results: tuple[CheckResult, ...] = ()
    observed_changed_paths: tuple[str, ...] = ()  # builder-reported; runtime verifies independently
    synchronization_prepared: bool = False
    execution_evidence_refs: tuple[str, ...] = ()


# --- Approval records (decision stages) ---


class UserDecision(StrictModel):
    """Generic runtime decision type. Chat text is never a UserDecision."""

    stage_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    reason: str = ""
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    user_identity: str = Field(min_length=1)
    decided_at: AwareDatetime


class ResearchApprovalRecord(StrictModel):
    decision: UserDecision
    research_proposal_ref: ArtifactRef
    research_proposal_digest: str = Field(min_length=1)
    research_execution_processing_plan_ref: ArtifactRef
    research_execution_processing_plan_digest: str = Field(min_length=1)
    source_checkpoint_ref: ArtifactRef
    source_checkpoint_hash: str = Field(min_length=1)

    @field_validator("decision")
    @classmethod
    def _decision_rules(cls, value: UserDecision) -> UserDecision:
        if value.stage_id != "research_approval":
            raise ValueError("decision must be addressed to research_approval")
        if value.action not in ("approve", "cancel"):
            raise ValueError("research_approval actions: approve, cancel")
        return value


class PlanApprovalRecord(StrictModel):
    decision: UserDecision
    frozen_plan_ref: ArtifactRef
    frozen_plan_hash: str = Field(min_length=1)
    implementation_plan_revision: int = Field(ge=1)
    build_execution_processing_plan_ref: ArtifactRef
    build_execution_processing_plan_digest: str = Field(min_length=1)
    source_checkpoint_ref: ArtifactRef
    source_checkpoint_hash: str = Field(min_length=1)
    preflight_result_ref: ArtifactRef
    preflight_result_digest: str = Field(min_length=1)
    approval_hash: str | None = None  # set by runtime on approve only

    @field_validator("decision")
    @classmethod
    def _decision_rules(cls, value: UserDecision) -> UserDecision:
        if value.stage_id != "plan_approval":
            raise ValueError("decision must be addressed to plan_approval")
        if value.action not in ("approve", "request_changes", "decline"):
            raise ValueError("plan_approval actions: approve, request_changes, decline")
        return value


class PendingDecision(StrictModel):
    """Durable decision request: the exact binding refs and digests captured
    when the run paused. A decision can land only while these remain current."""

    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    options: tuple[str, ...] = Field(min_length=1)
    requested_at: AwareDatetime
    timeout_seconds: int = Field(ge=1)
    binding_refs: Mapping[str, ArtifactRef] = Field(default_factory=dict)
    binding_digests: Mapping[str, str] = Field(default_factory=dict)


# --- Completion / terminal records ---


class CostSummary(StrictModel):
    tokens_used: int = Field(default=0, ge=0)
    tool_calls_used: int = Field(default=0, ge=0)
    # Per-stage attribution projection (completion-time; leaves are empty).
    by_stage: Mapping[str, CostSummary] = Field(default_factory=dict)


class CompletionInput(StrictModel):
    run: RunRef
    terminal_outcome: Literal["success", "partial", "cancelled", "failed"]
    input_refs: tuple[ArtifactRef, ...] = ()


class CompletionRecord(StrictModel):
    completion_outcome: Literal["success", "partial", "cancelled", "failed"]
    changed_paths: tuple[str, ...] = ()
    validation_results: tuple[CheckResult, ...] = ()
    criterion_results: tuple[CheckResult, ...] = ()
    remaining_work: tuple[str, ...] = ()
    retained_evidence: tuple[ArtifactRef, ...] = ()
    resulting_source_checkpoint: ArtifactRef | None = None
    cost_summary: CostSummary | None = None
    terminal_state: str = Field(min_length=1)
    completed_at: AwareDatetime


class FailureRecord(StrictModel):
    stage_id: str = Field(min_length=1)
    error_type: str = Field(min_length=1)
    evidence: str = ""
    resume_point: str | None = None
    occurred_at: AwareDatetime


class CancellationRecord(StrictModel):
    cancelled_by: Literal["user", "runtime"]
    reason: str = Field(min_length=1)
    partial_result_refs: tuple[ArtifactRef, ...] = ()
    occurred_at: AwareDatetime


class RunResult(StrictModel):
    run: RunRef
    terminal_state: Literal["completed", "cancelled", "failed"]
    reason: str = ""
    stages_visited: tuple[str, ...] = ()


class RunRecord(StrictModel):
    """Durable run state (runtime-owned).

    State transitions are CAS-guarded by the run store. The pinned
    definition triple (workflow_id, definition_version, definition_digest)
    is written at run start and never mutated afterwards
    (definition.mutation_after_run_start: prohibited).
    """

    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    definition_version: int = Field(ge=1)
    definition_digest: str = Field(min_length=1)
    state: RunState = RunState.CREATED
    current_stage: str | None = None
    stage_attempts: Mapping[str, int] = Field(default_factory=dict)
    stage_usage: Mapping[str, CostSummary] = Field(default_factory=dict)
    loop_counters: Mapping[str, int] = Field(default_factory=dict)
    tokens_used: int = Field(default=0, ge=0)
    tool_calls_used: int = Field(default=0, ge=0)
    terminal_outcome: Literal["success", "partial", "cancelled", "failed"] | None = None
    reason: str = ""
    resume_point: str | None = None
    initial_request_ref: ArtifactRef | None = None
    source_checkpoint_ref: ArtifactRef | None = None
    produced_artifacts: Mapping[str, ArtifactRef] = Field(default_factory=dict)
    created_at: AwareDatetime
    updated_at: AwareDatetime


# --- Events ---


class WorkflowEvent(StrictModel):
    event_type: EventType
    run_id: str = Field(min_length=1)
    stage_id: str | None = None
    attempt: int | None = Field(default=None, ge=1)
    payload: Mapping[str, Any] = Field(default_factory=dict)  # derived data, not a core contract
    occurred_at: AwareDatetime

    @property
    def persistence(self) -> EventPersistence:
        return self.event_type.persistence


# --- Backend interfaces and bindings ---


class TokenUsage(StrictModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)


class RoleBackendRequest(StrictModel):
    operation: str = Field(min_length=1)
    system_prompt: str = ""
    prompt: str = Field(min_length=1)
    output_schema: Mapping[str, Any]
    tool_names: tuple[str, ...] = ()
    max_tokens: int | None = Field(default=None, ge=1)


class RoleBackendResponse(StrictModel):
    structured_output: Mapping[str, Any] | None = None
    text: str = ""
    usage: TokenUsage = Field(default_factory=TokenUsage)
    provider: str = ""
    model: str = ""


class CodingBackendRequest(StrictModel):
    task: BuildTask
    sandbox_root: str = Field(min_length=1)
    prior_error: str = ""


class CodingBackendResult(StrictModel):
    execution_result: ExecutionResult
    observation: str = Field(min_length=1)
    reported_changed_paths: tuple[str, ...] = ()
    # Backend-reported usage for budget enforcement (builder accumulates it).
    usage: TokenUsage | None = None


class BackendBinding(StrictModel):
    binding_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    implementation: str = Field(min_length=1)
    package_name: str = Field(min_length=1)
    installed_version: str = Field(min_length=1)
    evaluation_ref: ArtifactRef | None = None
    evaluation_status: ExecutionResult = ExecutionResult.NOT_RUN
    permitted_operations: tuple[str, ...] = Field(min_length=1)
    required_capabilities: tuple[str, ...] = ()
    live_required: bool = False
    live_status: Literal["not_run", "valid", "failed"] = "not_run"
    binding_revision: int = Field(default=1, ge=1)
    approved_at: AwareDatetime | None = None


# --- Workflow definition records (typed view of breakdown.yaml) ---


class StageDefinition(StrictModel):
    """One declarative stage block.

    Core identity fields are strict; rich declarative policy blocks
    (transitions, bindings, criteria) are preserved as typed mappings
    owned by the definition file. Contracts derive behavior from them
    and never redeclare them.
    """

    id: str = Field(min_length=1)
    order: int = Field(ge=1)
    kind: ContractKind
    owner: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    requires: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    options: tuple[str, ...] = ()
    next: str | None = None
    precondition: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=1)
    computation_timeout_seconds: int | None = Field(default=None, ge=1)
    transitions: Mapping[str, Any] = Field(default_factory=dict)
    output_by_action: Mapping[str, tuple[str, ...]] = Field(default_factory=dict)
    decision_binding: Mapping[str, Any] | None = None
    processing_plan_activation: Mapping[str, Any] | None = None
    creates_processing_plan: Mapping[str, Any] | None = None
    completion_criteria: tuple[str, ...] = ()
    runtime_steps: tuple[Mapping[str, Any], ...] = ()
    on_failure: Mapping[str, Any] | None = None
    on_budget_exhausted: Mapping[str, Any] | None = None
    authorization_checks: tuple[str, ...] = ()
    execution_order: str | None = None
    stop_on_criterion: tuple[str, ...] = ()
    synchronization: Mapping[str, Any] | None = None
    accepts: Mapping[str, Any] | None = None
    records: tuple[str, ...] = ()
    emits: tuple[str, ...] = ()
    sub_roles: tuple[str, ...] = ()
    source_rules: Mapping[str, Any] | None = None
    delegation: Mapping[str, Any] | None = None
    budget_reserve: int | None = Field(default=None, ge=0)


class WorkflowDefinition(StrictModel):
    workflow_id: str = Field(min_length=1)
    definition_version: int = Field(ge=1)
    definition: Mapping[str, Any] = Field(default_factory=dict)
    vocabularies: Mapping[str, tuple[str, ...]] = Field(default_factory=dict)
    artifact_keys: Mapping[str, Any] = Field(default_factory=dict)
    digests: Mapping[str, Any] = Field(default_factory=dict)
    cost_budget: Mapping[str, Any] = Field(default_factory=dict)
    observability: Mapping[str, Any] = Field(default_factory=dict)
    processing_plan_schema: Mapping[str, Any] = Field(default_factory=dict)
    implementation_plan_schema: Mapping[str, Any] = Field(default_factory=dict)
    schema_validation: Mapping[str, Any] = Field(default_factory=dict)
    dependency_validation: Mapping[str, Any] = Field(default_factory=dict)
    stages: tuple[StageDefinition, ...] = Field(min_length=1)
    ownership: Mapping[str, Any] = Field(default_factory=dict)
    approval_boundary: Mapping[str, Any] = Field(default_factory=dict)
    handoff_rules: tuple[str, ...] = ()
    role_guidance: Mapping[str, Any] = Field(default_factory=dict)

    def stage_ids(self) -> tuple[str, ...]:
        return tuple(stage.id for stage in self.stages)

    def get_stage(self, stage_id: str) -> StageDefinition:
        for stage in self.stages:
            if stage.id == stage_id:
                return stage
        raise KeyError(stage_id)


# --- Operation -> typed I/O registry ---

OPERATION_IO: Mapping[str, tuple[type[StrictModel], type[StrictModel]]] = {
    "create_research_proposal": (ResearchProposalInput, ResearchProposalOutput),
    "review_research_findings": (FindingsReviewInput, FindingsReviewOutput),
    "execute_research": (ResearchExecutionInput, ResearchExecutionOutput),
    "analyze_code": (CodeAnalysisRequest, CodeAnalysisEvidence),
    "create_implementation_plan": (ImplementationPlanningInput, ImplementationPlanningOutput),
    "execute_build": (BuildExecutionInput, BuildExecutionOutput),
}
