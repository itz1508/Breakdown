"""Independent Coder agent for bounded, read-only code analysis.

Coder answers scoped code-interpretation requests with file evidence.
It does not select implementations, create build tasks, or modify source.
Workflow dispatch and permissions remain Runtime responsibilities.
"""

from __future__ import annotations
from breakdown.shared.model_loop import generate_structured, load_skill_prompt, render_json
from breakdown.shared.models import RoleBackend
from breakdown.shared.models import (
    CodeAnalysisEvidence,
    CodeAnalysisRequest,
    RoleBackendRequest,
    StageContext,
)
from breakdown.system.tools.toolkit import RoleToolkit

_CODER_BRIEF = load_skill_prompt(__file__)


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
        return await generate_structured(self, self._backend, request, CodeAnalysisEvidence)
