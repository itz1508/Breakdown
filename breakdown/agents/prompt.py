"""Compose the common source-grounded framework with a colocated role skill."""

from __future__ import annotations

from pathlib import Path


def _strip_front_matter(content: str) -> str:
    if not content.startswith("---\n"):
        return content.strip()
    parts = content.split("---\n", 2)
    if len(parts) != 3:
        raise ValueError("malformed SKILL.md front matter")
    return parts[2].strip()


def load_agent_prompt(module_file: str) -> str:
    """Load common guidance and the role's local skill without duplicating either."""
    module_path = Path(module_file).resolve()
    if module_path.name != "agent.py":
        raise ValueError(f"expected an agent.py module path, got {module_path}")

    package_root = module_path.parent.parent
    framework_path = package_root / "agents" / "WORKING_FRAMEWORK.md"
    skill_path = module_path.with_name("SKILL.md")

    framework = framework_path.read_text(encoding="utf-8").strip()
    skill = _strip_front_matter(skill_path.read_text(encoding="utf-8"))
    if not framework or not skill:
        raise ValueError(f"agent prompt sources must not be empty: {framework_path}, {skill_path}")

    return f"{framework}\n\n---\n\n{skill}"
