import ast
from pathlib import Path

from breakdown.agents.prompt import load_agent_prompt
from breakdown.builder.agent import Builder


def test_builder_is_independent_and_does_not_use_shared_model_loop() -> None:
    package = Path(__file__).resolve().parents[1]
    source_path = package / "agent.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert Builder.__module__ == "breakdown.builder.agent"
    assert "breakdown.shared.model_loop" not in imported
    assert (package / "SKILL.md").is_file()

def test_builder_prompt_includes_shared_and_role_guidance() -> None:
    package = Path(__file__).resolve().parents[1]
    prompt = load_agent_prompt(str(package / "agent.py"))
    assert "Source-Grounded Agent Working Framework" in prompt
    assert "Builder agent" in prompt
    assert "synchronize or copy changes out of the sandbox" in prompt
