from pathlib import Path

from breakdown.researcher.agent import Researcher


def test_researcher_package_owns_implementation_and_skill() -> None:
    package = Path(__file__).resolve().parents[1]
    assert Researcher.__module__ == "breakdown.researcher.agent"
    assert (package / "agent.py").is_file()
    assert (package / "SKILL.md").is_file()
