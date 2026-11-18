"""Coder: read-only supporting sub-role for bounded code analysis.

The Coder owns no workflow stage and produces no authoritative artifact.
It exists only inside findings_review, is invoked by the Auditor, and
returns evidence. Implementation selection, build-task creation, and file
modification are prohibited.
"""

from __future__ import annotations

from breakdown.contracts import RoleBackend
from breakdown.models import (
    CodeAnalysisEvidence,
    CodeAnalysisRequest,
    RoleBackendRequest,
    StageContext,
)
from breakdown.roles import RoleToolkit, render_json, structured_or_raise

_CODER_BRIEF = (
    "You are the Coder, a read-only analysis sub-role. Answer only bounded "
    "code-interpretation questions. Every claim traces to a file path and a "
    "symbol or line range. Do not propose refactors, select implementations, "
    "or create tasks. Uncertain behavior remains uncertain."
)


class Coder:
    def __init__(self, *, backend: RoleBackend, tools: RoleToolkit) -> None:
        self._backend = backend
        self._tools = tools

    async def analyze_code(self, input_value: CodeAnalysisRequest, context: StageContext) -> CodeAnalysisEvidence:
        prompt = (
            "Analyze code to answer one bounded question.\n"
            f"Question: {input_value.question}\n"
            f"Scope paths: {render_json(list(input_value.scope_paths))}\n"
            "Return file evidence for every claim."
        )
        request = RoleBackendRequest(
            operation="analyze_code",
            system_prompt=_CODER_BRIEF,
            prompt=prompt,
            output_schema=CodeAnalysisEvidence.model_json_schema(),
            tool_names=self._tools.allowed_names(),
        )
        response = await self._backend.generate(request)
        return structured_or_raise(response.structured_output, CodeAnalysisEvidence, "analyze_code")
