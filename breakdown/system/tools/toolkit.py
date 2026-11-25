"""Role-scoped access to the canonical system tool registry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from breakdown.system.tools.tools import ROLE_TOOL_ALLOWLIST, ToolNotAuthorized, dispatch_tool


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

