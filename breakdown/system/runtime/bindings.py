"""Backend binding records: evidence-backed selection of role implementations.

A backend may serve a role operation only when an approved BackendBinding
references a valid evaluation. Invalidation rules: package version
changed, evaluation missing or not completed, no permitted operations, or
live behavior required but still ``not_run``.
"""

from __future__ import annotations

import importlib.metadata
import json
from collections.abc import Mapping
from pathlib import Path

from pydantic import ValidationError

from breakdown.shared.models import BackendBinding, ExecutionResult


class BindingNotValid(RuntimeError):
    """A binding record failed validation rules."""


class BackendBindingStore:
    def __init__(self, bindings: Mapping[str, BackendBinding]) -> None:
        self._bindings = dict(bindings)

    @classmethod
    def load(cls, path: str | Path | None) -> BackendBindingStore:
        if path is None:
            return cls({})
        file_path = Path(path)
        if not file_path.exists():
            return cls({})
        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise BindingNotValid(f"bindings file is not valid JSON: {exc}") from exc
        if not isinstance(raw, list):
            raise BindingNotValid("bindings file must contain a JSON list of BackendBinding records")
        bindings: dict[str, BackendBinding] = {}
        for entry in raw:
            try:
                binding = BackendBinding.model_validate(entry)
            except ValidationError as exc:
                raise BindingNotValid(f"binding record rejected: {exc}") from exc
            if binding.binding_id in bindings:
                raise BindingNotValid(f"duplicate binding id {binding.binding_id!r}")
            bindings[binding.binding_id] = binding
        return cls(bindings)

    def for_role(self, role: str) -> BackendBinding | None:
        for binding in self._bindings.values():
            if binding.role == role:
                return binding
        return None

    def all(self) -> tuple[BackendBinding, ...]:
        return tuple(self._bindings.values())


def validate_binding(binding: BackendBinding) -> None:
    """Apply invalidation rules; raise BindingNotValid on any violation."""
    try:
        installed = importlib.metadata.version(binding.package_name)
    except importlib.metadata.PackageNotFoundError:
        raise BindingNotValid(
            f"binding {binding.binding_id}: package {binding.package_name!r} is not installed"
        ) from None
    if installed != binding.installed_version:
        raise BindingNotValid(
            f"binding {binding.binding_id}: installed version {installed} != recorded {binding.installed_version}"
        )
    if binding.evaluation_status is not ExecutionResult.COMPLETED:
        raise BindingNotValid(
            f"binding {binding.binding_id}: evaluation status is {binding.evaluation_status.value}, not completed"
        )
    if binding.evaluation_ref is None:
        raise BindingNotValid(f"binding {binding.binding_id}: missing evaluation reference")
    if not binding.permitted_operations:
        raise BindingNotValid(f"binding {binding.binding_id}: no permitted operations")
    if binding.live_required and binding.live_status != "valid":
        raise BindingNotValid(
            f"binding {binding.binding_id}: live check required but status is {binding.live_status!r}"
        )
