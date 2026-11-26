from pathlib import Path

from breakdown.planner.agent import Planner


def test_planner_package_owns_implementation_and_skill() -> None:
    package = Path(__file__).resolve().parents[1]
    assert Planner.__module__ == "breakdown.planner.agent"
    assert (package / "SKILL.md").is_file()
