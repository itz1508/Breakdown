"""Canonical SDK-neutral tool capabilities (Phase 1).

Each tool is one Python function with a typed input model. Role modules
choose their allowed subset; SDK adapters inside roles convert these
canonical capabilities into SDK-specific tool registrations. Authorization
(which role may call which tool) is wiring performed by bootstrap and is
distinct from the schema validation applied here to every input.

``source_checkpoint``, plan freeze/preflight, approval hashing, and
synchronization authorization are deterministic runtime operations — they
are never model-callable tools and never appear in this registry.

Containment policy is owned by ``safety.py``; this module delegates path
resolution and denied-name checks to it.
"""

from __future__ import annotations

import importlib.metadata
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import Field, ValidationError

from breakdown.models import StrictModel
from breakdown.safety import (
    SKIPPED_DIR_NAMES,
    ContainmentError,
    is_denied_read_name,
    resolve_contained,
)

MAX_FILE_BYTES = 1_000_000
MAX_RESULTS_DEFAULT = 50


class ToolInputNotValid(ValueError):
    """Raised when a tool payload fails schema validation."""


class ToolNotAuthorized(PermissionError):
    """Raised when a tool call escapes the containment boundary."""


def resolve_inside_root(root: Path, relative: str) -> Path:
    """Delegate to the safety boundary; translate containment errors."""
    try:
        return resolve_contained(root, relative)
    except ContainmentError as exc:
        raise ToolNotAuthorized(str(exc)) from exc


def _iter_text_files(root: Path) -> Sequence[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIPPED_DIR_NAMES for part in path.relative_to(root).parts):
            continue
        if is_denied_read_name(path.name):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        files.append(path)
    return files


# --- capability_inspect -----------------------------------------------------


class CapabilityInspectRequest(StrictModel):
    distribution: str = Field(min_length=1)


class CapabilityInspectReport(StrictModel):
    distribution: str
    installed: bool
    version: str | None = None
    summary: str | None = None


def capability_inspect(payload: CapabilityInspectRequest) -> CapabilityInspectReport:
    """Report an installed distribution's version without importing it."""
    try:
        distribution = importlib.metadata.distribution(payload.distribution)
    except importlib.metadata.PackageNotFoundError:
        return CapabilityInspectReport(distribution=payload.distribution, installed=False)
    summary = distribution.metadata["Summary"]
    return CapabilityInspectReport(
        distribution=payload.distribution,
        installed=True,
        version=distribution.version,
        summary=summary or None,
    )


# --- source_search -----------------------------------------------------------


class SourceSearchRequest(StrictModel):
    pattern: str = Field(min_length=1)
    max_results: int = Field(default=MAX_RESULTS_DEFAULT, ge=1, le=500)


class SourceSearchMatch(StrictModel):
    path: str
    line: int = Field(ge=1)
    text: str


class SourceSearchReport(StrictModel):
    matches: tuple[SourceSearchMatch, ...] = ()
    truncated: bool = False


def source_search(payload: SourceSearchRequest, *, root: Path) -> SourceSearchReport:
    """Regex search over text files strictly inside ``root``."""
    try:
        expression = re.compile(payload.pattern)
    except re.error as exc:
        raise ToolInputNotValid(f"invalid search pattern: {exc}") from exc
    matches: list[SourceSearchMatch] = []
    for file_path in _iter_text_files(root):
        try:
            text = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        relative = file_path.relative_to(root).as_posix()
        for number, line in enumerate(text.splitlines(), start=1):
            if expression.search(line):
                matches.append(SourceSearchMatch(path=relative, line=number, text=line.strip()[:300]))
                if len(matches) >= payload.max_results:
                    return SourceSearchReport(matches=tuple(matches), truncated=True)
    return SourceSearchReport(matches=tuple(matches), truncated=False)


# --- source_read -------------------------------------------------------------


class SourceReadRequest(StrictModel):
    path: str = Field(min_length=1)
    max_chars: int = Field(default=20_000, ge=1, le=200_000)


class SourceReadResult(StrictModel):
    path: str
    content: str
    size: int = Field(ge=0)
    truncated: bool = False


def source_read(payload: SourceReadRequest, *, root: Path) -> SourceReadResult:
    """Read one UTF-8 text file strictly inside ``root``."""
    resolved = resolve_inside_root(root, payload.path)
    if not resolved.is_file():
        raise ToolNotAuthorized(f"path does not identify a file: {payload.path}")
    if is_denied_read_name(resolved.name):
        raise ToolNotAuthorized("reading .env files is not allowed; settings are injected by the runtime")
    raw = resolved.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ToolNotAuthorized(f"file is not UTF-8 text: {payload.path}") from exc
    truncated = len(text) > payload.max_chars
    return SourceReadResult(
        path=PurePosixPath(payload.path.replace("\\", "/")).as_posix(),
        content=text[: payload.max_chars],
        size=len(raw),
        truncated=truncated,
    )


# --- registry ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CanonicalTool:
    name: str
    description: str
    input_model: type[StrictModel]
    function: Callable[..., Any]
    needs_root: bool = False


TOOLS: Mapping[str, CanonicalTool] = {
    "capability_inspect": CanonicalTool(
        name="capability_inspect",
        description="Report whether a Python distribution is installed and its version. Never imports the package.",
        input_model=CapabilityInspectRequest,
        function=capability_inspect,
    ),
    "source_search": CanonicalTool(
        name="source_search",
        description="Read-only regex search over text files inside the target repository.",
        input_model=SourceSearchRequest,
        function=source_search,
        needs_root=True,
    ),
    "source_read": CanonicalTool(
        name="source_read",
        description="Read one UTF-8 text file inside the target repository; .env and escapes are denied.",
        input_model=SourceReadRequest,
        function=source_read,
        needs_root=True,
    ),
}

# Allowed subsets per role (authorization wiring; bootstrap enforces).
ROLE_TOOL_ALLOWLIST: Mapping[str, tuple[str, ...]] = {
    "auditor": ("capability_inspect", "source_search", "source_read"),
    "researcher": ("source_search", "source_read"),
    "coder": ("source_search", "source_read"),
    "planner": ("capability_inspect", "source_search", "source_read"),
    "builder": (),
}


def tool_definitions() -> list[dict[str, Any]]:
    """SDK-neutral tool schemas for adapter conversion."""
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_model.model_json_schema(),
        }
        for tool in TOOLS.values()
    ]


def dispatch_tool(name: str, payload: Mapping[str, Any], *, root: Path) -> Any:
    """Validate the payload, then run the canonical tool."""
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolNotAuthorized(f"unknown tool: {name}")
    try:
        request = tool.input_model.model_validate(dict(payload))
    except ValidationError as exc:
        raise ToolInputNotValid(f"{name}: {exc}") from exc
    if tool.needs_root:
        return tool.function(request, root=root)
    return tool.function(request)
