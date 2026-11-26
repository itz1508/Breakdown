"""P2-T0 — canonical serialization and digest recipes, incl. JCS vectors."""

from __future__ import annotations

from datetime import UTC, datetime
from breakdown.shared.models import ImplementationPlan, SourceCheckpoint, UserDecision
from breakdown.system.storage.canonical import (
    approval_hash,
    canonical_bytes_from_dict,
    definition_digest,
    digest_dict,
    digest_model,
    digest_raw,
    frozen_plan_hash,
    SERIALIZER_PROFILE,
    source_checkpoint_hash,
)

def test_serializer_profile_pinned() -> None:
    assert SERIALIZER_PROFILE == "rfc8785-jcs-sha256-v1"


def test_jcs_key_ordering() -> None:
    assert canonical_bytes_from_dict({"b": 2, "a": 1}) == b'{"a":1,"b":2}'


def test_jcs_nested_ordering_and_no_whitespace() -> None:
    data = {"z": [3, {"b": 2, "a": 1}], "a": {"y": True, "x": None}}
    assert canonical_bytes_from_dict(data) == b'{"a":{"x":null,"y":true},"z":[3,{"a":1,"b":2}]}'


def test_jcs_insertion_order_irrelevant() -> None:
    assert digest_dict({"a": 1, "b": 2}) == digest_dict({"b": 2, "a": 1})


def test_jcs_unicode_literal() -> None:
    assert canonical_bytes_from_dict({"euro": "\u20ac"}) == '{"euro":"\u20ac"}'.encode("utf-8")


def test_jcs_float_es6_form() -> None:
    assert canonical_bytes_from_dict({"x": 1.0}) == b'{"x":1}'


def test_digest_raw_known_answer() -> None:
    assert digest_raw(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _checkpoint(**overrides: object) -> SourceCheckpoint:
    payload: dict[str, object] = {
        "repository_identity": "repo-a",
        "commit_sha": "c1",
        "file_hashes": {"src/x.py": "h1", "a/b.py": "h2"},
        "untracked_file_hashes": {"new.py": "h3"},
        "captured_at": datetime(2026, 11, 17, tzinfo=UTC),
    }
    payload.update(overrides)
    return SourceCheckpoint.model_validate(payload)


def _plan() -> ImplementationPlan:
    return ImplementationPlan.model_validate(
        {
            "plan_id": "p1",
            "revision": 1,
            "objective": "o",
            "requirement_refs": ["r1"],
            "source_checkpoint_ref": {"artifact_key": "source_checkpoint", "digest": "d" * 64},
            "tasks": [
                {
                    "task_id": "t1",
                    "sequence": 1,
                    "responsibility": "resp",
                    "requirement_refs": ["r1"],
                    "target_paths": [{"path": "src/x.py", "disposition": "modify"}],
                    "expected_result": "ok",
                    "validation_steps": [
                        {
                            "step_id": "v1",
                            "description": "d",
                            "command_or_observation": "c",
                            "expected": "e",
                        }
                    ],
                    "required_evidence": ["ev"],
                }
            ],
            "success_criteria": [{"criterion": "c"}],
        }
    )


def test_source_checkpoint_hash_stable_under_insertion_order() -> None:
    forward = _checkpoint(file_hashes={"src/x.py": "h1", "a/b.py": "h2"})
    reversed_order = _checkpoint(file_hashes={"a/b.py": "h2", "src/x.py": "h1"})
    assert source_checkpoint_hash(forward) == source_checkpoint_hash(reversed_order)


def test_source_checkpoint_hash_changes_with_content() -> None:
    assert source_checkpoint_hash(_checkpoint()) != source_checkpoint_hash(_checkpoint(commit_sha="c2"))


def test_frozen_plan_hash_binds_plan_checkpoint_version() -> None:
    plan = _plan()
    checkpoint = _checkpoint()
    base = frozen_plan_hash(plan, checkpoint, 1)
    assert base == frozen_plan_hash(plan, checkpoint, 1)
    assert base != frozen_plan_hash(plan, checkpoint, 2)
    assert base != frozen_plan_hash(plan, _checkpoint(commit_sha="other"), 1)


def test_approval_hash_binds_decision() -> None:
    decision = UserDecision(
        stage_id="plan_approval",
        action="approve",
        run_id="r",
        session_id="s",
        user_identity="u",
        decided_at=datetime(2026, 11, 17, tzinfo=UTC),
    )
    checkpoint = _checkpoint()
    base = approval_hash("f" * 64, checkpoint, decision)
    assert base == approval_hash("f" * 64, checkpoint, decision)
    declined = decision.model_copy(update={"action": "decline"})
    assert base != approval_hash("f" * 64, checkpoint, declined)
    assert base != approval_hash("e" * 64, checkpoint, decision)


def test_definition_digest_is_semantic() -> None:
    one = {"workflow_id": "x", "stages": [{"id": "a"}]}
    reordered = {"stages": [{"id": "a"}], "workflow_id": "x"}
    assert definition_digest(one) == definition_digest(reordered)
    changed = {"workflow_id": "x", "stages": [{"id": "b"}]}
    assert definition_digest(one) != definition_digest(changed)


def test_canonical_model_matches_dict_dump() -> None:
    checkpoint = _checkpoint()
    from breakdown.system.storage.canonical import canonical_bytes

    assert canonical_bytes(checkpoint) == canonical_bytes_from_dict(checkpoint.model_dump(mode="json"))
    assert digest_model(checkpoint) == digest_dict(checkpoint.model_dump(mode="json"))
