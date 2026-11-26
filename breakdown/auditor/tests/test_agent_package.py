from pathlib import Path

from breakdown.auditor.agent import Auditor


def test_auditor_is_not_bound_to_a_coder_subrole() -> None:
    package = Path(__file__).resolve().parents[1]
    assert Auditor.__module__ == "breakdown.auditor.agent"
    assert "coder" not in Auditor.__init__.__annotations__
    assert (package / "SKILL.md").is_file()
