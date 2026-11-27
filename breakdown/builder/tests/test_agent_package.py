import ast
from pathlib import Path

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
