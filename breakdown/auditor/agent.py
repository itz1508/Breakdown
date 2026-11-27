"""Auditor role: two typed operations on one SDK-native chain.

Stages: research_proposal (create_research_proposal) and findings_review
(review_research_findings). Auditor prepares specifications and compares
accepted research findings with repository evidence.

The Auditor never writes files, never selects implementation
architecture, and never creates build tasks. Source checkpoints and
digests are deterministic runtime facts, not Auditor outputs.
"""

from __future__ import annotations

from breakdown.shared.base import RoleOperationError
from breakdown.shared.model_loop import generate_structured, load_skill_prompt, render_json
from breakdown.shared.models import (
    FindingStatus,
    FindingsReviewInput,
    FindingsReviewOutput,
    ResearchProposalInput,
    ResearchProposalOutput,
    RoleBackend,
    RoleBackendRequest,
    StageContext,
)
from breakdown.system.tools.toolkit import RoleToolkit

_AUDITOR_BRIEF = load_skill_prompt(__file__)


class Auditor:
    def __init__(self, *, backend: RoleBackend, tools: RoleToolkit) -> None:
        self._backend = backend
        self._tools = tools

    async def create_research_proposal(
        self, input_value: ResearchProposalInput, context: StageContext
    ) -> ResearchProposalOutput:
        prompt = (
            "Create the bounded research proposal for this request.\n"
            f"Exact request:\n{input_value.initial_request.text}\n\n"
            "Split the request into single candidate requirements. Inspect the Python standard "
            "library, installed distributions, and current repository implementations using the "
            "available tools. Treat capability inspection as distribution presence/version evidence, "
            "not API behavior. Check public SDK APIs only when authoritative documentation or source "
            "is actually available in the supplied context or tools; otherwise retain uncertainty "
            "and create a focused research question. Do not claim unavailable sources were inspected. "
            "Map uncertainty to research questions."
        )
        request = RoleBackendRequest(
            operation="create_research_proposal",
            system_prompt=_AUDITOR_BRIEF,
            prompt=prompt,
            output_schema=ResearchProposalOutput.model_json_schema(),
            tool_names=self._tools.allowed_names(),
        )
        output = await generate_structured(self, self._backend, request, ResearchProposalOutput)
        _validate_proposal(output)
        return output

    async def review_research_findings(
        self, input_value: FindingsReviewInput, context: StageContext
    ) -> FindingsReviewOutput:
        proposal = input_value.research_proposal.model_dump(mode="json")
        research_record = input_value.research_record.model_dump(mode="json")
        checkpoint_context = {
            "repository_identity": input_value.source_checkpoint.repository_identity,
            "commit_sha": input_value.source_checkpoint.commit_sha,
            "captured_at": input_value.source_checkpoint.captured_at.isoformat(),
            "tracked_file_count": len(input_value.source_checkpoint.file_hashes),
            "untracked_file_count": len(input_value.source_checkpoint.untracked_file_hashes),
        }
        prompt = (
            "Review the research record against the original accepted requirements.\\n"
            f"Exact user intent:\\n{input_value.exact_user_intent}\\n\\n"
            f"Accepted proposal and candidate requirements:\\n{render_json(proposal)}\\n\\n"
            f"Research record, evidence and provenance:\\n{render_json(research_record)}\\n\\n"
            f"Repository source checkpoint:\\n{render_json(checkpoint_context)}\\n\\n"
            "Classify every candidate requirement. Validate that material claims trace to "
            "evidence, preserve all contradictions and unresolved questions, and keep fixture "
            "provenance. Do not select architecture, create implementation tasks, or convert "
            "missing evidence into a supported finding."
        )
        request = RoleBackendRequest(
            operation="review_research_findings",
            system_prompt=_AUDITOR_BRIEF,
            prompt=prompt,
            output_schema=FindingsReviewOutput.model_json_schema(),
            tool_names=self._tools.allowed_names(),
        )
        output = await generate_structured(self, self._backend, request, FindingsReviewOutput)
        # Carry forward verified pre-normalized evidence from the Researcher if not overwritten
        if not output.normalized_evidence and input_value.research_record.normalized_evidence:
            output = output.model_copy(update={"normalized_evidence": input_value.research_record.normalized_evidence})
        _validate_findings(output, input_value)
        return output


def _validate_proposal(output: ResearchProposalOutput) -> None:
    requirement_ids = [
        requirement.requirement_id for requirement in output.candidate_requirements
    ]
    if len(requirement_ids) != len(set(requirement_ids)):
        raise RoleOperationError("candidate requirement ids must be unique")

    question_ids = [question.question_id for question in output.research_questions]
    if len(question_ids) != len(set(question_ids)):
        raise RoleOperationError("research question ids must be unique")

    known_requirements = set(requirement_ids)
    for requirement in output.candidate_requirements:
        if requirement.research_question_ref and requirement.research_question_ref not in question_ids:
            raise RoleOperationError("coverage uncertainty must reference a declared research question")

    for responsibility in output.candidate_source_responsibilities:
        unknown = set(responsibility.requirement_refs) - known_requirements
        if unknown:
            raise RoleOperationError(
                f"source responsibilities reference unknown requirements: {sorted(unknown)}"
            )


def _validate_findings(output: FindingsReviewOutput, input_value: FindingsReviewInput) -> None:
    proposal = input_value.research_proposal
    research = input_value.research_record
    known_requirement_ids = {
        requirement.requirement_id for requirement in proposal.candidate_requirements
    }
    finding_ids = [finding.finding_id for finding in output.classified_findings]
    if len(finding_ids) != len(set(finding_ids)):
        raise RoleOperationError("finding ids must be unique")

    finding_requirement_ids = {finding.requirement_ref for finding in output.classified_findings}
    unknown_requirement_refs = finding_requirement_ids - known_requirement_ids
    missing_requirement_refs = known_requirement_ids - finding_requirement_ids
    if unknown_requirement_refs or missing_requirement_refs:
        raise RoleOperationError(
            "classified findings must cover exactly the accepted requirements; "
            f"missing={sorted(missing_requirement_refs)}, unknown={sorted(unknown_requirement_refs)}"
        )

    evidence_by_id = {evidence.evidence_id: evidence for evidence in research.evidence}
    if len(evidence_by_id) != len(research.evidence):
        raise RoleOperationError("research evidence identifiers must be unique")
    known_evidence_ids = set(evidence_by_id)
    for finding in output.classified_findings:
        referenced_evidence = {
            trace_step.evidence_ref
            for trace_step in finding.decision_trace
            if trace_step.evidence_ref
        }
        if finding.status is not FindingStatus.UNRESOLVED and not referenced_evidence:
            raise RoleOperationError(
                f"finding {finding.finding_id!r} requires evidence for status {finding.status.value!r}"
            )
        for evidence_ref in referenced_evidence:
            if evidence_ref not in known_evidence_ids:
                raise RoleOperationError(
                    f"finding {finding.finding_id!r} references unknown evidence {evidence_ref!r}"
                )

    input_contradictions = {
        (item.topic, item.positions, item.evidence_refs)
        for item in research.contradictions
    }
    output_contradictions = {
        (item.topic, item.positions, item.evidence_refs)
        for item in output.contradictions_preserved
    }
    if not input_contradictions <= output_contradictions:
        missing = input_contradictions - output_contradictions
        raise RoleOperationError(f"contradictions must be preserved exactly: {sorted(missing)}")
    for contradiction in output.contradictions_preserved:
        unknown_refs = set(contradiction.evidence_refs) - known_evidence_ids
        if unknown_refs:
            raise RoleOperationError(
                f"contradiction {contradiction.topic!r} references unknown evidence: "
                f"{sorted(unknown_refs)}"
            )

    input_fixtures = {fixture.fixture_id: fixture for fixture in research.fixture_specifications}
    output_fixtures = {
        fixture.fixture_id: fixture for fixture in output.reviewed_fixture_specifications
    }
    if len(input_fixtures) != len(research.fixture_specifications) or len(output_fixtures) != len(
        output.reviewed_fixture_specifications
    ):
        raise RoleOperationError("fixture identifiers must be unique")
    if set(input_fixtures) != set(output_fixtures):
        raise RoleOperationError(
            "reviewed fixture specifications must preserve source fixture identifiers; "
            f"missing={sorted(set(input_fixtures) - set(output_fixtures))}, "
            f"unknown={sorted(set(output_fixtures) - set(input_fixtures))}"
        )
    changed_fixtures = [
        fixture_id
        for fixture_id, source_fixture in input_fixtures.items()
        if output_fixtures[fixture_id] != source_fixture
    ]
    if changed_fixtures:
        raise RoleOperationError(
            f"reviewed fixture specifications changed Researcher-owned content: {sorted(changed_fixtures)}"
        )

    input_unresolved = {
        question.question_id: question for question in research.unresolved_questions
    }
    output_unresolved = {
        question.question_id: question for question in output.reviewed_unresolved_questions
    }
    if len(input_unresolved) != len(research.unresolved_questions) or len(output_unresolved) != len(
        output.reviewed_unresolved_questions
    ):
        raise RoleOperationError("unresolved question identifiers must be unique")
    if set(input_unresolved) != set(output_unresolved):
        raise RoleOperationError(
            "reviewed unresolved questions must preserve source question identifiers; "
            f"missing={sorted(set(input_unresolved) - set(output_unresolved))}, "
            f"unknown={sorted(set(output_unresolved) - set(input_unresolved))}"
        )
    changed_questions = [
        question_id
        for question_id, source_question in input_unresolved.items()
        if output_unresolved[question_id] != source_question
    ]
    if changed_questions:
        raise RoleOperationError(
            "reviewed unresolved questions must preserve exact source content: "
            f"{sorted(changed_questions)}"
        )

    if output.normalized_evidence:
        normalized_by_ref = {
            item.evidence_ref: item for item in output.normalized_evidence
        }
        if len(normalized_by_ref) != len(output.normalized_evidence):
            raise RoleOperationError("normalized evidence references must be unique")
        if set(normalized_by_ref) != known_evidence_ids:
            raise RoleOperationError(
                "normalized evidence must cover exactly the Researcher evidence identifiers"
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
