"""Role processors: one typed executable chain per role.

Roles import only models, contracts, and tools — never engine, bootstrap,
or each other (the AST boundary test enforces this). A role receives its
backend and tool subset by construction; it cannot silently select another
backend. Roles never persist artifacts and never invoke the next workflow
role directly; contracts activate roles and the runtime owns progression.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from breakdown.tools import ROLE_TOOL_ALLOWLIST, ToolNotAuthorized, dispatch_tool

T = TypeVar("T", bound=BaseModel)


class RoleOperationError(RuntimeError):
    """A role chain produced or received something the contract rejects."""


@dataclass(frozen=True, slots=True)
class RoleToolkit:
    """Per-role authorized view over the canonical tools."""

    role: str
    root: Path
    memory_root: Path | None = None

    def allowed_names(self) -> tuple[str, ...]:
        return ROLE_TOOL_ALLOWLIST.get(self.role, ())

    def call(self, name: str, payload: Mapping[str, Any]) -> Any:
        if name not in self.allowed_names():
            raise ToolNotAuthorized(f"tool {name!r} is not allowed for role {self.role!r}")
        return dispatch_tool(name, payload, root=self.root, memory_root=self.memory_root)


def structured_or_raise(raw: Mapping[str, Any] | None, model: type[T], operation: str) -> T:
    """Validate backend structured output against the authoritative model."""
    if raw is None:
        raise RoleOperationError(f"backend returned no structured output for {operation}")
    try:
        return model.model_validate(dict(raw))
    except ValidationError as exc:
        raise RoleOperationError(f"backend output rejected by {model.__name__}: {exc}") from exc


async def generate_structured(role: Any, backend: Any, request: Any, model: type[T]) -> T:
    """One SDK round-trip on the role's native chain: generate, capture the
    backend-reported usage on the role (runtime budget enforcement reads it),
    and validate the structured output against the authoritative model."""
    response = await backend.generate(request)
    role.last_usage = response.usage
    return structured_or_raise(response.structured_output, model, request.operation)


def render_json(value: Any, limit: int = 50_000) -> str:
    """Deterministic prompt rendering for backend inputs."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    text = str(value) if not isinstance(value, (dict, list)) else _dumps(value)
    return text[:limit]


def _dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
