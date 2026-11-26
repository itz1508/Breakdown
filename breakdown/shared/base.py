"""Shared strict model base and agent-operation errors."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION = "1"


class StrictModel(BaseModel):
    """Base for authoritative contracts: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION


class RoleOperationError(RuntimeError):
    """An agent chain produced or received something its contract rejects."""
