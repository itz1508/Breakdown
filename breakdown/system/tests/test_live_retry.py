"""Phase 3b — D38: live transport retry for transient rate-limit and server errors.

The adapter owns the retry policy (SDK-internal retries are disabled on the
client): 429, connection, and 5xx errors are retried up to three times with
exponential backoff, honoring Retry-After when present. Exhaustion surfaces as
LiveBackendError so the engine's stage recovery takes over.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from openai import AsyncOpenAI
from breakdown.shared.models import CodingBackendRequest, ExecutionResult, RoleBackendRequest
from breakdown.system.runtime.live_backend import LiveBackendError, OpenAICompatibleCodingBackend, OpenAICompatibleRoleBackend

def _completion(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": "test-model",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url="http://mock.local/v1",
        api_key="sk-test",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_retries=0,  # D38: adapter-owned retry policy; SDK retries disabled
    )


def _request() -> RoleBackendRequest:
    return RoleBackendRequest(
        operation="retry_probe",
        system_prompt="system",
        prompt="user prompt",
        output_schema={"type": "object", "properties": {"answer": {"type": "integer"}}},
    )


def _backend(handler: Callable[[httpx.Request], httpx.Response], tmp_path: Path) -> OpenAICompatibleRoleBackend:
    return OpenAICompatibleRoleBackend(
        client=_client(handler), model="test-model", tool_root=tmp_path, retry_base_delay=0.0
    )


def _coding_request(sandbox: Path) -> CodingBackendRequest:
    from breakdown.shared.models import BuildTask

    (sandbox / "src").mkdir(parents=True, exist_ok=True)
    task = BuildTask.model_validate(
        {
            "task_id": "task-1",
            "sequence": 1,
            "responsibility": "add subtract",
            "requirement_refs": ["req-1"],
            "target_paths": [{"path": "src/calc.py", "disposition": "modify"}],
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


def test_transient_rate_limit_is_retried_until_success(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json=_completion('{"answer": 42}'))

    response = asyncio.run(_backend(handler, tmp_path).generate(_request()))
    assert response.structured_output == {"answer": 42}
    assert calls["n"] == 3  # initial attempt + 2 retries


def test_persistent_rate_limit_exhausts_retries(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"error": "rate limited"})

    with pytest.raises(LiveBackendError, match="live API call failed"):
        asyncio.run(_backend(handler, tmp_path).generate(_request()))
    assert calls["n"] == 4  # initial attempt + 3 retries, then exhausted


def test_retry_after_header_is_honored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    delays: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": "rate limited"}, headers={"Retry-After": "7"})
        return httpx.Response(200, json=_completion('{"answer": 1}'))

    backend = OpenAICompatibleRoleBackend(
        client=_client(handler), model="test-model", tool_root=tmp_path, retry_base_delay=0.5
    )
    response = asyncio.run(backend.generate(_request()))
    assert response.structured_output == {"answer": 1}
    assert delays == [7.0]


def test_coding_backend_retries_transient_errors(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        payload = json.dumps({"src/calc.py": "def subtract(a, b):\n    return a - b\n"})
        return httpx.Response(200, json=_completion(payload))

    backend = OpenAICompatibleCodingBackend(client=_client(handler), model="test-model", retry_base_delay=0.0)
    result = asyncio.run(backend.apply_task(_coding_request(sandbox)))
    assert result.execution_result is ExecutionResult.COMPLETED
    assert calls["n"] == 2
    assert result.reported_changed_paths == ("src/calc.py",)
