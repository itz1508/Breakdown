"""Regression coverage for common and role-specific agent prompt composition."""

from pathlib import Path

from breakdown.agents.prompt import load_agent_prompt
from breakdown.shared.model_loop import load_skill_prompt

BREAKDOWN_ROOT = Path(__file__).resolve().parents[1]
ROLE_NAMES = ("auditor", "researcher", "planner", "coder", "builder")


def _role_skill_body(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    if content.startswith("---\n"):
        parts = content.split("---\n", 2)
        if len(parts) != 3:
            raise AssertionError(f"malformed skill front matter: {path}")
        content = parts[2]
    return content.strip()


def test_every_role_receives_shared_framework_and_colocated_skill() -> None:
    framework = (BREAKDOWN_ROOT / "agents" / "WORKING_FRAMEWORK.md").read_text(encoding="utf-8").strip()

    for role_name in ROLE_NAMES:
        package = BREAKDOWN_ROOT / role_name
        module_path = package / "agent.py"
        source = module_path.read_text(encoding="utf-8")
        skill_body = _role_skill_body(package / "SKILL.md")

        if role_name == "builder":
            assert "load_agent_prompt(__file__)" in source
            prompt = load_agent_prompt(str(module_path))
        else:
            assert "load_skill_prompt(__file__)" in source
            prompt = load_skill_prompt(str(module_path))

        assert prompt == f"{framework}\n\n---\n\n{skill_body}"
