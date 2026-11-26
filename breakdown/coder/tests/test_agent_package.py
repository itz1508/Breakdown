from pathlib import Path

from breakdown.coder.agent import Coder


def test_coder_has_an_independent_package() -> None:
    package = Path(__file__).resolve().parents[1]
    assert Coder.__module__ == "breakdown.coder.agent"
    assert (package / "SKILL.md").is_file()
