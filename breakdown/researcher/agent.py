"""Researcher role: one typed operation on one SDK-native chain.

Stage: research_execution. The Researcher investigates only approved
questions, records provenance for material claims, preserves
contradictions, and keeps missing information unresolved. It does not
create subagents; it uses only the Host-supplied read-only tool set.
Synthetic samples never become evidence.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from breakdown.shared.base import RoleOperationError
from breakdown.shared.model_loop import generate_structured, load_skill_prompt, render_json
from breakdown.shared.models import (
    BaselineMap,
    NormalizedEvidence,
    ResearchExecutionInput,
    ResearchExecutionOutput,
    ResearchRecord,
    RoleBackend,
    RoleBackendRequest,
    ScaffoldingEntry,
    SourceCheckpoint,
    StageContext,
)
from breakdown.system.tools.toolkit import RoleToolkit

_RESEARCHER_BRIEF = load_skill_prompt(__file__)


def _build_baseline_map(
    checkpoint: SourceCheckpoint,
    root: Path | None = None,
) -> BaselineMap:
    """Build an authoritative BaselineMap scaffolding inventory from repo state."""
    entries: list[ScaffoldingEntry] = []
    for file_path in sorted(checkpoint.file_hashes.keys()):
        p = file_path.lower()
        if "test" in p:
            category = "test"
            resp = "Automated test module"
        elif p.endswith(".py"):
            category = "source"
            resp = "Application source module"
        elif p.endswith((".yaml", ".yml", ".json", ".toml", ".ini")):
            category = "config"
            resp = "Configuration specification"
        elif p.endswith((".md", ".rst", ".txt")):
            category = "doc"
            resp = "Documentation"
        else:
            category = "other"
            resp = "Project asset"

        exports: list[str] = []
        exports_status: Literal[
            "not_applicable", "not_attempted", "complete", "unavailable", "syntax_invalid", "out_of_scope"
        ] = "not_applicable"
        if p.endswith(".py"):
            exports_status = "not_attempted"
            if root is not None:
                resolved_root = root.resolve()
                full_path = (resolved_root / file_path).resolve()
                try:
                    full_path.relative_to(resolved_root)
                except ValueError:
                    exports_status = "out_of_scope"
                else:
                    try:
                        source = full_path.read_text(encoding="utf-8")
                    except (OSError, UnicodeError):
                        exports_status = "unavailable"
                    else:
                        try:
                            tree = ast.parse(source)
                        except SyntaxError:
                            exports_status = "syntax_invalid"
                        else:
                            exports = [
                                node.name
                                for node in ast.iter_child_nodes(tree)
                                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                                and not node.name.startswith("_")
                            ]
                            exports_status = "complete"

        entries.append(
            ScaffoldingEntry(
                path=file_path,
                category=category,
                responsibility=resp,
                exports=tuple(exports),
                exports_status=exports_status,
            )
        )

    return BaselineMap(
        repository_identity=checkpoint.repository_identity,
        entries=tuple(entries),
        created_at=datetime.now(UTC),
    )


def _normalize_evidence(record: ResearchRecord) -> tuple[NormalizedEvidence, ...]:
    """Normalize evidence without allowing reference or provenance drift."""
    evidence_by_id = {evidence.evidence_id: evidence for evidence in record.evidence}
    if len(evidence_by_id) != len(record.evidence):
        raise RoleOperationError("research evidence identifiers must be unique")

    if not record.normalized_evidence:
        return tuple(
            NormalizedEvidence(
                evidence_ref=evidence.evidence_id,
                normalized_form=evidence.claim,
                source_identity=evidence.source_identity,
                source_location=evidence.source_location,
                source_version=evidence.source_version,
                provenance_preserved=True,
            )
            for evidence in record.evidence
        )

    normalized_by_ref = {
        evidence.evidence_ref: evidence for evidence in record.normalized_evidence
    }
    if len(normalized_by_ref) != len(record.normalized_evidence):
        raise RoleOperationError("normalized evidence references must be unique")

    missing = set(evidence_by_id) - set(normalized_by_ref)
    unknown = set(normalized_by_ref) - set(evidence_by_id)
    if missing or unknown:
        raise RoleOperationError(
            f"normalized evidence references do not match source evidence; "
            f"missing={sorted(missing)}, unknown={sorted(unknown)}"
        )

    for evidence_ref, normalized in normalized_by_ref.items():
        source = evidence_by_id[evidence_ref]
        if (
            normalized.source_identity != source.source_identity
            or normalized.source_location != source.source_location
            or normalized.source_version != source.source_version
        ):
            raise RoleOperationError(
                f"normalized evidence {evidence_ref!r} changed source provenance"
            )

    return record.normalized_evidence


class Researcher:
    def __init__(self, *, backend: RoleBackend, tools: RoleToolkit) -> None:
        self._backend = backend
        self._tools = tools

    async def execute_research(
        self, input_value: ResearchExecutionInput, context: StageContext
    ) -> ResearchExecutionOutput:
        proposal = input_value.research_proposal.model_dump(mode="json")
        processing_plan = input_value.processing_plan.model_dump(mode="json")
        checkpoint_context = {
            "repository_identity": input_value.source_checkpoint.repository_identity,
            "commit_sha": input_value.source_checkpoint.commit_sha,
            "captured_at": input_value.source_checkpoint.captured_at.isoformat(),
            "tracked_file_count": len(input_value.source_checkpoint.file_hashes),
            "untracked_file_count": len(input_value.source_checkpoint.untracked_file_hashes),
        }
        approval_ref = input_value.research_approval_ref.model_dump(mode="json")
        prompt = (
            "Answer only the research questions in the accepted proposal. Preserve the exact "
            "requirements and research scope; do not perform implementation planning.\n"
            f"Accepted research proposal and requirements:\n{render_json(proposal)}\n\n"
            f"Approved processing plan:\n{render_json(processing_plan)}\n\n"
            f"Approval reference:\n{render_json(approval_ref)}\n\n"
            f"Source checkpoint context:\n{render_json(checkpoint_context)}\n\n"
            "For every approved question, return either an evidence-backed resolution or an "
            "explicit unresolved record. Cite exact source identities and locations, distinguish "
            "direct observation from inference, preserve contradictions, and never invent sources."
        )
        request = RoleBackendRequest(
            operation="execute_research",
            system_prompt=_RESEARCHER_BRIEF,
            prompt=prompt,
            output_schema=ResearchExecutionOutput.model_json_schema(),
            tool_names=self._tools.allowed_names(),
        )
        output = await generate_structured(self, self._backend, request, ResearchExecutionOutput)

        # Baseline mapping and evidence normalization ownership (D40)
        record = output.research_record
        baseline_map = record.baseline_map or _build_baseline_map(
            input_value.source_checkpoint, getattr(self._tools, "root", None)
        )
        norm_evidence = _normalize_evidence(record)
        updated_record = record.model_copy(
            update={
                "baseline_map": baseline_map,
                "normalized_evidence": norm_evidence,
            }
        )
        output = output.model_copy(update={"research_record": updated_record})

        _validate_coverage(output, input_value)
        return output


def _validate_coverage(output: ResearchExecutionOutput, input_value: ResearchExecutionInput) -> None:
    record = output.research_record
    approved = {question.question_id for question in input_value.research_proposal.research_questions}
    resolved_ids = [question.question_id for question in record.resolved_questions]
    unresolved_ids = [question.question_id for question in record.unresolved_questions]
    resolved = set(resolved_ids)
    unresolved = set(unresolved_ids)
    todo_ids = [item.question_id for item in output.research_todo.items]
    if len(resolved_ids) != len(resolved) or len(unresolved_ids) != len(unresolved):
        raise RoleOperationError("research question identifiers must be unique within each outcome")
    if len(todo_ids) != len(set(todo_ids)) or set(todo_ids) != approved:
        raise RoleOperationError("research todo must contain each approved question exactly once")
    unfinished = [
        item.question_id
        for item in output.research_todo.items
        if item.status in {ExecutionStatus.NOT_RUN, ExecutionStatus.IN_PROGRESS}
    ]
    if unfinished:
        raise RoleOperationError(
            f"research todo contains questions not processed to a terminal state: {sorted(unfinished)}"
        )

    addressed = resolved | unresolved
    missing = approved - addressed
    unknown = addressed - approved
    if missing or unknown:
        raise RoleOperationError(
            f"research question coverage differs from approved scope; "
            f"missing={sorted(missing)}, unknown={sorted(unknown)}"
        )
    overlap = resolved & unresolved
    if overlap:
        raise RoleOperationError(f"questions cannot be both resolved and unresolved: {sorted(overlap)}")

    evidence_ids = {evidence.evidence_id for evidence in record.evidence}
    if len(evidence_ids) != len(record.evidence):
        raise RoleOperationError("research evidence identifiers must be unique")
    for question in record.resolved_questions:
        unknown_refs = set(question.evidence_refs) - evidence_ids
        if unknown_refs:
            raise RoleOperationError(
                f"resolved question {question.question_id!r} references unknown evidence: "
                f"{sorted(unknown_refs)}"
            )
    for contradiction in record.contradictions:
        unknown_refs = set(contradiction.evidence_refs) - evidence_ids
        if unknown_refs:
            raise RoleOperationError(
                f"contradiction {contradiction.topic!r} references unknown evidence: "
                f"{sorted(unknown_refs)}"
            )

    for evidence in record.evidence:
        if not evidence.source_identity or not evidence.source_location:
            raise RoleOperationError(
                f"material finding {evidence.evidence_id} missing provenance "
                "(source_identity or source_location)"
            )
