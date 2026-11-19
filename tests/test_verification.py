"""Phase 3b - D35: verification blocks sync."""

import pytest
from pathlib import Path
import tempfile
import shutil

from breakdown.engine import WorkflowEngine, EngineStores, load_workflow
from breakdown.models import (
    CheckResult,
    CriterionResult,
    ExecutionResult,
    RunState,
    RunRecord,
    TokenUsage,
)
from breakdown.artifact_store import ArtifactStore
from breakdown.events import EventStore
from breakdown.safety import SafetyBoundary
from breakdown.memory import MemoryStore


def test_verifier_rejection_blocks_sync():
    """D35: verifier rejection blocks sync despite builder claiming valid."""
    tmp = Path(tempfile.mkdtemp())
    try:
        target = tmp / "repo"
        target.mkdir(parents=True)
        (target / "src").mkdir()

        state = tmp / "state"
        artifacts = ArtifactStore(state)
        events = EventStore(state)
        runs_store = ...  # RunStore initialization
        safety = SafetyBoundary(target_root=target, state_root=state)
        memory = MemoryStore(state)

        definition = load_workflow("breakdown.yaml")

        from breakdown.contracts import build_contract_registry
        from breakdown.approvals import Approvals
        from breakdown.bootstrap import build_runtime

        contracts = build_contract_registry(definition)
        approvals = Approvals(...)
        runtime = build_runtime(definition, contracts, approvals, memory)
        engine = WorkflowEngine(
            definition=definition,
            contracts=contracts,
            stores=runtime.stores,
            approvals=approvals,
            role_factory=runtime.role_factory,
        )

        record = engine.start_run("test request", user_identity="u")

        # Builder reports all tasks valid
        # Verifier returns not_valid for one criterion
        # Run should end failed
        assert record.state == RunState.failed
        assert "independent verifier" in (record.reason or "")
        # No files should be synced
        finally:
            shutil.rmtree(tmp)


def test_verifier_absence_preserves_legacy():
    """D35: existing rows without verifier key still pass (backward compat)."""
    # Set up engine WITHOUT "verifier" in role_factory
    # Run existing lifecycle rows should still pass unchanged
    pass


def test_verifier_failure_is_conservative():
    """D35: verifier backend raises -> terminal failed, no crash."""
    # Set up engine with verifier that raises exception
    # Run should end failed with "independent verifier unavailable"
    # Never a crash, never authorization
    pass


def test_prompt_embeds_sandbox_not_builder():
    """D35: verification input embeds sandbox files, not builder observations."""
    from breakdown.verification import build_verification_input
    pass


def test_verifier_happy_path_authorizes_sync():
    """D35: builder + verifier all valid -> sync authorized, run succeeds."""
    # Set up engine WITH "verifier" in role_factory
    # Builder reports all tasks valid
    # Verifier returns all valid
    # integration_valid = True stored as independent_verification artifact
    # Usage attributed to build stage
    # Run completes successfully with files synchronized
    pass