"""Scoreboard semantics: every blocking zero must be exercised by a case."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent.parent / "evals"


def _load_scorers():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("evals_scorers", EVALS_DIR / "scorers.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["evals_scorers"] = module
    spec.loader.exec_module(module)
    return module


def test_unscored_zero_fails_the_run() -> None:
    scorers = _load_scorers()
    board = scorers.BlockingScoreboard()
    board.scored("auditor_invented_paths")
    failures = board.report()
    # Seven zeros have no exercising case -> each counts as a failure.
    assert failures == 7


def test_scored_zero_with_no_violations_holds() -> None:
    scorers = _load_scorers()
    board = scorers.BlockingScoreboard()
    for zero in scorers.BLOCKING_ZEROS:
        board.scored(zero)
    assert board.report() == 0


def test_violation_counts_and_unknown_zero_raises() -> None:
    scorers = _load_scorers()
    board = scorers.BlockingScoreboard()
    for zero in scorers.BLOCKING_ZEROS:
        board.scored(zero)
    board.violate("builder_unexpected_paths", "test violation")
    assert board.report() == 1
    try:
        board.violate("not_a_zero")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass
