"""Shared structured-model execution helpers used by non-Builder agents."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from breakdown.shared.base import RoleOperationError

T = TypeVar("T", bound=BaseModel)


def structured_or_raise(raw: dict[str, Any] | None, model: type[T], operation: str) -> T:
    """Validate backend structured output against the authoritative model."""
    if raw is None:
        raise RoleOperationError(f"backend returned no structured output for {operation}")
    try:
        return model.model_validate(dict(raw))
    except ValidationError as exc:
        raise RoleOperationError(f"backend output rejected by {model.__name__}: {exc}") from exc


async def generate_structured(role: Any, backend: Any, request: Any, model: type[T]) -> T:
    """Run one model turn, capture usage, and validate structured output."""
    response = await backend.generate(request)
    role.last_usage = response.usage
    return structured_or_raise(response.structured_output, model, request.operation)


def render_json(value: Any, limit: int = 50_000) -> str:
    """Deterministic prompt rendering for backend inputs."""
    import json
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    text = str(value) if not isinstance(value, (dict, list)) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return text[:limit]


def load_skill_prompt(module_file: str) -> str:
    """Load the colocated SKILL.md as the single agent-instruction source."""
    content = (Path(module_file).with_name("SKILL.md")).read_text(encoding="utf-8")
    if content.startswith("---\n"):
        _, _, content = content.split("---\n", 2)
    return content.strip()
