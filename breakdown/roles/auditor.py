"""Auditor role: two typed operations on one SDK-native chain.

Stages: research_proposal (create_research_proposal) and findings_review
(review_research_findings). Coder is the Auditor's read-only sub-role for
bounded code interpretation inside findings_review.

The Auditor never writes files, never selects implementation
architecture, and never creates build tasks. Source checkpoints and
digests are deterministic runtime facts, not Auditor outputs.
"""

from __future__ import annotations

from typing import Protocol

from breakdown.contracts import RoleBackend
from breakdown.models import (
    CodeAnalysisEvidence,
    CodeAnalysisRequest,
    FindingsReviewInput,
    FindingsReviewOutput,
    ResearchProposalInput,
    ResearchProposalOutput,
    RoleBackendRequest,
    StageContext,
)
from breakdown.roles import RoleOperationError, RoleToolkit, generate_structured, render_json

_AUDITOR_BRIEF = (
    "You are the Auditor. Inspect before claiming. Preserve the exact user request. "
    "Classify capability coverage as covered, partial, not_covered, or uncertainty. "
    "Uncertainty becomes a research question. Never invent paths, sources, or results. "
    "Never select implementation architecture or create build tasks."
)


class _CodeAnalyzer(Protocol):
    """Structural type for the Coder sub-role (avoids sibling-role imports)."""

    async def analyze_code(self, request: CodeAnalysisRequest, context: StageContext) -> CodeAnalysisEvidence: ...


class Auditor:
    def __init__(self, *, backend: RoleBackend, tools: RoleToolkit, coder: _CodeAnalyzer | None = None) -> None:
        self._backend = backend
        self._tools = tools
        self._coder = coder

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
        prompt = (
            "Review the research findings.\n"
            f"Research record:\n{render_json(input_value.research_record)}\n\n"
            "Classify each finding, normalize evidence while preserving provenance, keep "
            "contradictions visible, and carry unresolved questions forward. Produce no "
            "architecture selection and no build tasks."
        )
        request = RoleBackendRequest(
            operation="review_research_findings",
            system_prompt=_AUDITOR_BRIEF,
            prompt=prompt,
            output_schema=FindingsReviewOutput.model_json_schema(),
            tool_names=self._tools.allowed_names(),
        )
        output = await generate_structured(self, self._backend, request, FindingsReviewOutput)
        _validate_findings(output, input_value)
        return output

    async def invoke_coder(self, request: CodeAnalysisRequest, context: StageContext) -> CodeAnalysisEvidence:
        """Explicit bounded sub-role invocation; Coder owns no stage."""
        if self._coder is None:
            raise RoleOperationError("no coder sub-role binding available for findings review")
        return await self._coder.analyze_code(request, context)


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
