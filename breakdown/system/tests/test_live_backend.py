"""Phase 3a — live OpenAI-compatible backends over a mock transport (no network)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest
from openai import AsyncOpenAI
from breakdown.shared.models import (
    CodingBackendRequest,
    ExecutionResult,
    RoleBackendRequest,
    Settings,
)
from breakdown.system.runtime.live_backend import (
    build_openai_client,
    LiveBackendError,
    OpenAICompatibleCodingBackend,
    OpenAICompatibleRoleBackend,
    resolve_model,
    tool_schemas,
)

SECRET = "sk-live-super-secret-value"


def _completion(content: str | None = None, tool_calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": "test-model",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


def _tool_call(name: str, arguments: Mapping[str, Any], call_id: str = "call_1") -> dict[str, Any]:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def _client(handler) -> AsyncOpenAI:  # type: ignore[no-untyped-def]
    transport = httpx.MockTransport(handler)
    return AsyncOpenAI(
        base_url="http://mock.local/v1",
        api_key=SECRET,
        http_client=httpx.AsyncClient(transport=transport),
    )


def _request(tool_names: tuple[str, ...] = ()) -> RoleBackendRequest:
    return RoleBackendRequest(
        operation="test_operation",
        system_prompt="system",
        prompt="user prompt",
        output_schema={"type": "object", "properties": {"answer": {"type": "integer"}}},
        tool_names=tool_names,
    )


def test_structured_output_and_usage_mapping() -> None:
    import asyncio

    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=_completion(content='{"answer": 42}'))

    backend = OpenAICompatibleRoleBackend(client=_client(handler), model="test-model", tool_root=Path("."))
    response = asyncio.run(backend.generate(_request()))
    assert response.structured_output == {"answer": 42}
    assert response.usage.input_tokens == 11
    assert response.usage.output_tokens == 7
    assert response.usage.tool_calls == 0
    assert response.provider == "openai_compatible"
    assert response.model == "test-model"
    assert bodies[0]["model"] == "test-model"
    assert bodies[0]["messages"][0] == {"role": "system", "content": "system"}


def test_tool_loop_dispatches_canonical_tools(tmp_path: Path) -> None:
    import asyncio

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if len(bodies) == 1:
            assert body["tools"][0]["function"]["name"] == "source_read"
            return httpx.Response(
                200, json=_completion(tool_calls=[_tool_call("source_read", {"path": "src/calc.py"})])
            )
        return httpx.Response(200, json=_completion(content='{"answer": 1}'))

    backend = OpenAICompatibleRoleBackend(client=_client(handler), model="m", tool_root=tmp_path)
    response = asyncio.run(backend.generate(_request(tool_names=("source_read",))))
    assert response.structured_output == {"answer": 1}
    assert response.usage.tool_calls == 1
    tool_messages = [message for message in bodies[1]["messages"] if message["role"] == "tool"]
    assert len(tool_messages) == 1
    assert "def add" in tool_messages[0]["content"]


def test_unauthorized_tool_request_rejected() -> None:
    import asyncio

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion(tool_calls=[_tool_call("source_read", {"path": "x"})]))

    backend = OpenAICompatibleRoleBackend(client=_client(handler), model="m", tool_root=Path("."))
    with pytest.raises(LiveBackendError, match="unauthorized tool"):
        asyncio.run(backend.generate(_request(tool_names=())))  # no tools authorized


def test_tool_round_exhaustion() -> None:
    import asyncio

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion(tool_calls=[_tool_call("source_read", {"path": "src/calc.py"})]))

    backend = OpenAICompatibleRoleBackend(client=_client(handler), model="m", tool_root=Path("."), max_tool_rounds=2)
    with pytest.raises(LiveBackendError, match="exceeded 2 rounds"):
        asyncio.run(backend.generate(_request(tool_names=("source_read",))))


def test_json_schema_fallback_when_endpoint_rejects() -> None:
    import asyncio

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "response_format" in body:
            return httpx.Response(400, json={"error": {"message": "response_format unsupported"}})
        if body["messages"][-1]["content"].startswith("Return the final answer"):
            return httpx.Response(200, json=_completion(content='{"answer": 7}'))
        return httpx.Response(200, json=_completion(content="prose, not json"))

    backend = OpenAICompatibleRoleBackend(client=_client(handler), model="m", tool_root=Path("."))
    response = asyncio.run(backend.generate(_request()))
    assert response.structured_output == {"answer": 7}


def test_malformed_final_output_returns_none() -> None:
    import asyncio

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion(content="I cannot produce JSON."))

    backend = OpenAICompatibleRoleBackend(client=_client(handler), model="m", tool_root=Path("."))
    response = asyncio.run(backend.generate(_request()))
    assert response.structured_output is None  # role layer rejects via structured_or_raise


def _coding_request(sandbox: Path, target: str = "src/calc.py") -> CodingBackendRequest:
    from breakdown.shared.models import BuildTask

    task = BuildTask.model_validate(
        {
            "task_id": "task-1",
            "sequence": 1,
            "responsibility": "add subtract",
            "requirement_refs": ["req-1"],
            "target_paths": [{"path": target, "disposition": "modify"}],
            "source_evidence": ["f-1"],
            "capability_reuse": [],
            "reference_ids": [],
            "expected_result": "subtract works",
            "validation_steps": [
                {"step_id": "v-1", "description": "d", "command_or_observation": "c", "expected": "e"}
            ],
            "required_evidence": ["obs"],
        }
    )
    return CodingBackendRequest(task=task, sandbox_root=str(sandbox), prior_error="")


def test_coding_backend_confines_writes_to_approved_paths(tmp_path: Path) -> None:
    import asyncio

    sandbox = tmp_path / "sandbox"
    (sandbox / "src").mkdir(parents=True)
    (sandbox / "src" / "calc.py").write_text("old", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.dumps({"src/calc.py": "new content", "evil.txt": "rogue"})
        return httpx.Response(200, json=_completion(content=payload))

    backend = OpenAICompatibleCodingBackend(client=_client(handler), model="m")
    result = asyncio.run(backend.apply_task(_coding_request(sandbox)))
    assert result.execution_result is ExecutionResult.FAILED
    assert "unauthorized paths" in result.observation
    assert not (sandbox / "evil.txt").exists()
    assert (sandbox / "src" / "calc.py").read_text(encoding="utf-8") == "old"  # nothing written on overreach


def test_coding_backend_writes_approved_path(tmp_path: Path) -> None:
    import asyncio

    sandbox = tmp_path / "sandbox"
    (sandbox / "src").mkdir(parents=True)
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        payload = json.dumps({"src/calc.py": "def subtract(a, b):\\n    return a - b\\n"})
        return httpx.Response(200, json=_completion(content=payload))

    backend = OpenAICompatibleCodingBackend(client=_client(handler), model="m")
    coding_request = _coding_request(sandbox).model_copy(
        update={"agent_instructions": "Builder-specific instructions."}
    )
    result = asyncio.run(backend.apply_task(coding_request))
    assert bodies[0]["messages"][0]["content"].startswith("Builder-specific instructions.")
    assert "Execution invariant" in bodies[0]["messages"][0]["content"]
    assert result.execution_result is ExecutionResult.COMPLETED
    assert result.reported_changed_paths == ("src/calc.py",)
    assert "def subtract" in (sandbox / "src" / "calc.py").read_text(encoding="utf-8")
    assert result.usage is not None and result.usage.input_tokens == 11


def test_secret_never_appears_in_configuration_errors() -> None:
    settings = Settings(api_key=SECRET)  # base_url missing
    with pytest.raises(LiveBackendError, match="BREAKDOWN_API_BASE_URL") as excinfo:
        build_openai_client(settings)
    assert SECRET not in str(excinfo.value)
    with pytest.raises(LiveBackendError, match="BREAKDOWN_API_KEY"):
        build_openai_client(Settings(api_base_url="http://x/v1"))
    with pytest.raises(LiveBackendError, match="BREAKDOWN_MODEL"):
        resolve_model(Settings(), "auditor")
    assert resolve_model(Settings(model="base"), "auditor") == "base"
    assert resolve_model(Settings(model="base", model_auditor="tier-a"), "auditor") == "tier-a"


def test_tool_schemas_derive_from_registry() -> None:
    schemas = tool_schemas(("source_read", "source_search"))
    assert [schema["function"]["name"] for schema in schemas] == ["source_read", "source_search"]
    assert all(schema["type"] == "function" for schema in schemas)
    assert schemas[0]["function"]["parameters"]["type"] == "object"
    with pytest.raises(LiveBackendError, match="unknown tool"):
        tool_schemas(("ghost_tool",))
