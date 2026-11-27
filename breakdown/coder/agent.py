"""Independent Coder agent for bounded, read-only code analysis.

Coder answers scoped code-interpretation requests with file evidence.
It does not select implementations, create build tasks, or modify source.
Workflow dispatch and permissions remain Runtime responsibilities.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from breakdown.shared.base import RoleOperationError
from breakdown.shared.model_loop import generate_structured, load_skill_prompt, render_json
from breakdown.shared.models import (
    CodeAnalysisEvidence,
    CodeAnalysisRequest,
    RoleBackend,
    RoleBackendRequest,
    StageContext,
    validate_target_path,
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
        _validate_evidence_scope(output, input_value, self._tools)
        return output


def _validate_evidence_scope(
    output: CodeAnalysisEvidence,
    input_value: CodeAnalysisRequest,
    tools: RoleToolkit,
) -> None:
    """Verify that every cited excerpt is readable and inside the requested scope."""
    root = tools.root.resolve()
    normalized_scopes: list[tuple[PurePosixPath, bool]] = []
    for raw_scope in input_value.scope_paths:
        normalized = _normalize_scope_path(raw_scope)
        resolved = (root / normalized).resolve()
        if not resolved.is_relative_to(root) or not resolved.exists():
            raise RoleOperationError(
                f"code-analysis scope path {raw_scope!r} is missing or outside the repository"
            )
        normalized_scopes.append((PurePosixPath(normalized), resolved.is_dir()))

    for evidence in output.file_evidence:
        normalized_path = _normalize_scope_path(evidence.path)
        evidence_path = PurePosixPath(normalized_path)
        resolved_evidence = (root / normalized_path).resolve()
        if not resolved_evidence.is_relative_to(root) or not resolved_evidence.is_file():
            raise RoleOperationError(
                f"code evidence path {evidence.path!r} is not a readable repository file"
            )

        in_scope = any(
            evidence_path == scope
            or (is_directory and scope in evidence_path.parents)
            for scope, is_directory in normalized_scopes
        )
        if not in_scope:
            raise RoleOperationError(
                f"code evidence path {evidence.path!r} is outside requested scope "
                f"{[scope.as_posix() for scope, _ in normalized_scopes]}"
            )

        source = tools.call("source_read", {"path": normalized_path, "max_chars": 200_000})
        if evidence.excerpt not in source.content:
            qualifier = "bounded read" if source.truncated else "source file"
            raise RoleOperationError(
                f"code evidence excerpt for {evidence.path!r} does not occur in the {qualifier}"
            )

        line_match = re.search(
            r"\\blines?\\s+(\\d+)(?:\\s*[-–]\\s*(\\d+))?",
            evidence.locator,
            flags=re.IGNORECASE,
        )
        if line_match:
            start_line = int(line_match.group(1))
            end_line = int(line_match.group(2) or start_line)
            lines = source.content.splitlines()
            if start_line < 1 or end_line < start_line or end_line > len(lines):
                raise RoleOperationError(
                    f"code evidence locator {evidence.locator!r} is outside {evidence.path!r}"
                )
            located_text = "\\n".join(lines[start_line - 1 : end_line])
            if evidence.excerpt not in located_text:
                raise RoleOperationError(
                    f"code evidence excerpt does not match locator {evidence.locator!r} "
                    f"in {evidence.path!r}"
                )


def _normalize_scope_path(path: str) -> str:
    try:
        return validate_target_path(path)
    except ValueError as exc:
        raise RoleOperationError(f"invalid code-analysis path {path!r}: {exc}") from exc
