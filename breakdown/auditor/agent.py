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
            "Split the request into single candidate requirements. For each, check the Python "
            "standard library, installed distributions, and public SDK APIs before proposing any "
            "custom responsibility. Map uncertainty to research questions."
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
    ids = [requirement.requirement_id for requirement in output.candidate_requirements]
    if len(ids) != len(set(ids)):
        raise RoleOperationError("candidate requirement ids must be unique")
    question_ids = {question.question_id for question in output.research_questions}
    for requirement in output.candidate_requirements:
        if requirement.research_question_ref and requirement.research_question_ref not in question_ids:
            raise RoleOperationError("coverage uncertainty must reference a declared research question")


def _validate_findings(output: FindingsReviewOutput, input_value: FindingsReviewInput) -> None:
    input_topics = {contradiction.topic for contradiction in input_value.research_record.contradictions}
    preserved_topics = {contradiction.topic for contradiction in output.contradictions_preserved}
    missing = input_topics - preserved_topics
    if missing:
        raise RoleOperationError(f"contradictions must be preserved: {sorted(missing)}")
    ids = [finding.finding_id for finding in output.classified_findings]
    if len(ids) != len(set(ids)):
        raise RoleOperationError("finding ids must be unique")
    known_requirement_ids = {
        requirement.requirement_id for requirement in input_value.research_proposal.candidate_requirements
    }
    unknown_requirement_refs = {
        finding.requirement_ref for finding in output.classified_findings
    } - known_requirement_ids
    if unknown_requirement_refs:
        raise RoleOperationError(
            f"classified findings reference unknown requirements: {sorted(unknown_requirement_refs)}"
        )
