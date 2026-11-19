"""Researcher role: one typed operation on one SDK-native chain.

Stage: research_execution. The Researcher investigates only approved
questions, records provenance for material claims, preserves
contradictions, and keeps missing information unresolved. Delegation is
bounded (max 3 parallel workers, 3 rounds, read-only, evidence input
only). Synthetic samples never become evidence.
"""

from __future__ import annotations

from breakdown.contracts import RoleBackend
from breakdown.models import (
    ResearchExecutionInput,
    ResearchExecutionOutput,
    RoleBackendRequest,
    StageContext,
)
from breakdown.roles import RoleOperationError, RoleToolkit, generate_structured, render_json

_RESEARCHER_BRIEF = (
    "You are the Researcher. Investigate only the approved research questions. "
    "Every material claim carries provenance: source identity, location, version. "
    "Preserve contradictions. Missing information stays unresolved; never guess it away. "
    "Synthetic samples are never evidence. Select no implementation. "
    "If memory tools are available, consult prior-run lessons (memory_list, "
    "memory_read, memory_search) for previously resolved questions."
)


class Researcher:
    def __init__(self, *, backend: RoleBackend, tools: RoleToolkit) -> None:
        self._backend = backend
        self._tools = tools

    async def execute_research(
        self, input_value: ResearchExecutionInput, context: StageContext
    ) -> ResearchExecutionOutput:
        questions = [question.model_dump(mode="json") for question in input_value.research_proposal.research_questions]
        prompt = (
            "Answer every approved research question.\n"
            f"Questions:\n{render_json(questions)}\n\n"
            "Record evidence with provenance, preserve contradictions, and list "
            "unresolved questions explicitly."
        )
        request = RoleBackendRequest(
            operation="execute_research",
            system_prompt=_RESEARCHER_BRIEF,
            prompt=prompt,
            output_schema=ResearchExecutionOutput.model_json_schema(),
            tool_names=self._tools.allowed_names(),
        )
        output = await generate_structured(self, self._backend, request, ResearchExecutionOutput)
        _validate_coverage(output, input_value)
        return output


def _validate_coverage(output: ResearchExecutionOutput, input_value: ResearchExecutionInput) -> None:
    record = output.research_record
    approved = {question.question_id for question in input_value.research_proposal.research_questions}
    resolved = {question.question_id for question in record.resolved_questions}
    unresolved = {question.question_id for question in record.unresolved_questions}
    missing = approved - (resolved | unresolved)
    if missing:
        raise RoleOperationError(f"every approved question must be addressed; missing: {sorted(missing)}")
    overlap = resolved & unresolved
    if overlap:
        raise RoleOperationError(f"questions cannot be both resolved and unresolved: {sorted(overlap)}")
