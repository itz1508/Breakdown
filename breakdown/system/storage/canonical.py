"""Canonical serialization and digest recipes.

Ported from ``d:\\breakdown\\system\\storage\\canonical_serialization.py``
(RFC 8785 / JCS via the ``rfc8785`` package, SHA-256), extended with the
workflow's digest recipes. Every digest-bearing artifact computes its
digest only through this module — never with ad-hoc serialization.

Recipes (reconciled between the def-1 seed ``digests:`` block and the v7
``defined_hashes`` recipes; seed identity components win where they add
fields — Decision D16/D17):

- definition_digest      = sha256(canonical_json(parsed workflow definition))
- artifact_content_hash  = sha256(canonical artifact bytes)
- source_checkpoint_hash = sha256(canonical_json(identity tuple))
- frozen_plan_hash       = sha256(canonical_json(plan + checkpoint hash + definition_version))
- approval_hash          = sha256(canonical_json(frozen_plan_hash + approved checkpoint hash + decision record))
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any, TypeVar

import rfc8785
from pydantic import BaseModel

from breakdown.shared.models import ImplementationPlan, SourceCheckpoint, UserDecision

SERIALIZER_PROFILE = "rfc8785-jcs-sha256-v1"
DIGEST_ALGORITHM = "sha256"

T = TypeVar("T", bound=BaseModel)


def canonical_bytes_from_dict(data: Mapping[str, Any]) -> bytes:
    """Canonicalize a mapping to RFC 8785 JSON bytes."""
    return rfc8785.dumps(dict(data))


def canonical_bytes(model: BaseModel) -> bytes:
    """Canonicalize a model (JSON-mode dump first) to RFC 8785 bytes."""
    return rfc8785.dumps(model.model_dump(mode="json"))


def digest_raw(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_dict(data: Mapping[str, Any]) -> str:
    return digest_raw(canonical_bytes_from_dict(data))


def digest_model(model: BaseModel) -> str:
    return digest_raw(canonical_bytes(model))


def definition_digest(definition: Mapping[str, Any]) -> str:
    """Semantic pin: digest of the parsed definition, not raw file bytes.

    Survives whitespace/comment reformatting; changes when any declared
    field changes (Decision D17, per the v7 defined_hashes recipe).
    """
    return digest_dict(definition)


def source_checkpoint_hash(checkpoint: SourceCheckpoint) -> str:
    """Digest over the seed's full identity tuple (Decision D16)."""
    payload = {
        "repository_identity": checkpoint.repository_identity,
        "commit_sha": checkpoint.commit_sha or "",
        "sorted_file_hashes": [f"{path}:{digest}" for path, digest in sorted(checkpoint.file_hashes.items())],
        "relevant_untracked_path_hashes": [
            f"{path}:{digest}" for path, digest in sorted(checkpoint.untracked_file_hashes.items())
        ],
    }
    return digest_dict(payload)


def frozen_plan_hash(plan: ImplementationPlan, checkpoint: SourceCheckpoint, definition_version: int) -> str:
    """Bind the plan to its checkpoint and definition version."""
    payload = {
        "implementation_plan": plan.model_dump(mode="json"),
        "source_checkpoint_hash": source_checkpoint_hash(checkpoint),
        "definition_version": definition_version,
    }
    return digest_dict(payload)


def approval_hash(frozen_plan_hash_value: str, approved_checkpoint: SourceCheckpoint, decision: UserDecision) -> str:
    """Bind the user decision to the exact frozen package it approved."""
    payload = {
        "frozen_plan_hash": frozen_plan_hash_value,
        "approved_source_checkpoint_hash": source_checkpoint_hash(approved_checkpoint),
        "user_decision_record": decision.model_dump(mode="json"),
    }
    return digest_dict(payload)
