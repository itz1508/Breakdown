from __future__ import annotations

import pytest
from pydantic import ValidationError
from breakdown.shared.base import StrictModel
from breakdown.shared.config import Settings
from breakdown.shared.models import CodingBackend, RoleBackend

def test_shared_model_base_rejects_unknown_fields() -> None:
    class Example(StrictModel):
        value: str

    with pytest.raises(ValidationError):
        Example(value="ok", unexpected=True)


def test_settings_are_owned_by_shared_config() -> None:
    assert Settings.__module__ == "breakdown.shared.config"


def test_backend_protocols_are_owned_by_shared_models() -> None:
    assert RoleBackend.__module__ == "breakdown.shared.models"
    assert CodingBackend.__module__ == "breakdown.shared.models"
