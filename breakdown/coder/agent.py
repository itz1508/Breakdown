"""Independent Coder agent for bounded, read-only code analysis.

Coder answers scoped code-interpretation requests with file evidence.
It does not select implementations, create build tasks, or modify source.
Workflow dispatch and permissions remain Runtime responsibilities.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from breakdown.shared.base import RoleOperationError
from breakdown.shared.model_loop import generate_structured, load_skill_prompt, render_json
from breakdown.shared.models import RoleBackend, validate_target_path
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
        output = await generate_structured(self, self._backend, request, CodeAnalysisEvidence)
        _validate_evidence_scope(output, input_value)
        return output


def _validate_evidence_scope(output: CodeAnalysisEvidence, input_value: CodeAnalysisRequest) -> None:
    """Reject evidence paths outside the exact code-analysis scope."""
    normalized_scopes: tuple[PurePosixPath, ...] = tuple(
        PurePosixPath(_normalize_scope_path(path)) for path in input_value.scope_paths
    )
    for evidence in output.file_evidence:
        evidence_path = PurePosixPath(_normalize_scope_path(evidence.path))
        if not any(
            evidence_path == scope or scope in evidence_path.parents
            for scope in normalized_scopes
        ):
            raise RoleOperationError(
                f"code evidence path {evidence.path!r} is outside requested scope "
                f"{[scope.as_posix() for scope in normalized_scopes]}"
            )


def _normalize_scope_path(path: str) -> str:
    try:
        return validate_target_path(path)
    except ValueError as exc:
        raise RoleOperationError(f"invalid code-analysis path {path!r}: {exc}") from exc
