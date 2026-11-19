"""Live OpenAI-compatible backends (Phase 3a, D30).

Rebuilds the reference orchestration pattern's worker leg on any
OpenAI-compatible chat API — Databricks Model Serving, custom gateways
(LiteLLM/vLLM/Ollama-style), or OpenAI directly. The engine remains the
orchestrator; these adapters are the workers: one SDK-native chain per
role, structured outputs validated by the authoritative models, and a
bounded canonical tool loop.

Secrets: the API key travels as pydantic SecretStr and is only ever
materialized inside the client. Error messages name environment
variables, never values.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel

from breakdown.models import (
    CodingBackendRequest,
    CodingBackendResult,
    ExecutionResult,
    RoleBackendRequest,
    RoleBackendResponse,
    Settings,
    TokenUsage,
)
from breakdown.tools import TOOLS, dispatch_tool


class LiveBackendError(RuntimeError):
    """Live adapter failure: configuration, transport, or protocol."""


def build_openai_client(settings: Settings) -> AsyncOpenAI:
    """One shared client per runtime; key materialized only here."""
    if not settings.api_base_url:
        raise LiveBackendError("live mode requires BREAKDOWN_API_BASE_URL (e.g. a Databricks serving endpoint)")
    if settings.api_key is None:
        raise LiveBackendError("live mode requires BREAKDOWN_API_KEY")
    return AsyncOpenAI(base_url=settings.api_base_url, api_key=settings.api_key.get_secret_value())


def resolve_model(settings: Settings, role: str) -> str:
    """Per-role model tier (D32): BREAKDOWN_MODEL_<ROLE> override, else BREAKDOWN_MODEL."""
    override = getattr(settings, f"model_{role}", None)
    model = override or settings.model
    if not model:
        raise LiveBackendError(f"live mode requires BREAKDOWN_MODEL (or BREAKDOWN_MODEL_{role.upper()})")
    return model


def tool_schemas(tool_names: Sequence[str]) -> list[dict[str, Any]]:
    """OpenAI function-tool definitions derived from the canonical registry."""
    schemas: list[dict[str, Any]] = []
    for name in tool_names:
        tool = TOOLS.get(name)
        if tool is None:
            raise LiveBackendError(f"unknown tool in request: {name!r}")
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_model.model_json_schema(),
                },
            }
        )
    return schemas


def _try_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class OpenAICompatibleRoleBackend:
    """RoleBackend over one OpenAI-compatible chat endpoint.

    Shape: bounded tool rounds over the canonical tools, then a structured
    final answer. Structured mode prefers response_format json_schema
    (strict); endpoints that reject it fall back to prompt-JSON. Pydantic
    validation in the role layer remains the authority on output shape.
    """

    def __init__(self, *, client: AsyncOpenAI, model: str, tool_root: Path, max_tool_rounds: int = 8) -> None:
        self._client = client
        self._model = model
        self._tool_root = Path(tool_root)
        self._max_tool_rounds = max_tool_rounds

    async def generate(self, request: RoleBackendRequest) -> RoleBackendResponse:
        allowed = tuple(request.tool_names)
        tools = tool_schemas(allowed) if allowed else None
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": request.system_prompt or "You complete one bounded workflow operation."},
            {"role": "user", "content": request.prompt},
        ]
        tokens = {"input": 0, "output": 0}
        tool_calls_used = 0
        rounds = 0
        text = ""
        while True:
            response = await self._create(messages=messages, tools=tools)
            self._accumulate(response, tokens)
            message = response.choices[0].message
            if not message.tool_calls:
                text = message.content or ""
                break
            rounds += 1
            if rounds > self._max_tool_rounds:
                raise LiveBackendError(f"tool loop exceeded {self._max_tool_rounds} rounds for {request.operation}")
            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.function.name, "arguments": call.function.arguments},
                        }
                        for call in message.tool_calls
                    ],
                }
            )
            for call in message.tool_calls:
                if call.function.name not in allowed:
                    raise LiveBackendError(f"model requested unauthorized tool {call.function.name!r}")
                tool_calls_used += 1
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": self._dispatch(call.function.name, call.function.arguments),
                    }
                )
        structured = await self._structured_final(request, messages, text, tokens)
        return RoleBackendResponse(
            structured_output=structured,
            text=text,
            usage=TokenUsage(input_tokens=tokens["input"], output_tokens=tokens["output"], tool_calls=tool_calls_used),
            provider="openai_compatible",
            model=self._model,
        )

    async def _create(self, *, messages: list[dict[str, Any]], tools: Any = None, response_format: Any = None) -> Any:
        kwargs: dict[str, Any] = {"model": self._model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        if response_format is not None:
            kwargs["response_format"] = response_format
        try:
            return await self._client.chat.completions.create(**kwargs)
        except LiveBackendError:
            raise
        except Exception as exc:  # transport / auth / protocol errors
            raise LiveBackendError(f"live API call failed for model {self._model!r}: {type(exc).__name__}") from exc

    @staticmethod
    def _accumulate(response: Any, tokens: dict[str, int]) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        tokens["input"] += int(getattr(usage, "prompt_tokens", 0) or 0)
        tokens["output"] += int(getattr(usage, "completion_tokens", 0) or 0)

    def _dispatch(self, name: str, arguments_json: str) -> str:
        """Canonical tool dispatch; errors are returned to the model, not raised."""
        try:
            payload = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"invalid tool arguments: {exc}"})
        if not isinstance(payload, dict):
            return json.dumps({"error": "tool arguments must be a JSON object"})
        try:
            result = dispatch_tool(name, payload, root=self._tool_root)
        except Exception as exc:
            return json.dumps({"error": str(exc)})
        if isinstance(result, BaseModel):
            return json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
        return json.dumps(result, ensure_ascii=False, default=str)

    async def _structured_final(
        self,
        request: RoleBackendRequest,
        messages: list[dict[str, Any]],
        text: str,
        tokens: dict[str, int],
    ) -> Mapping[str, Any] | None:
        candidate = _try_json_object(text)
        if candidate is not None:
            return candidate
        final_messages = [
            *messages,
            {
                "role": "user",
                "content": "Return the final answer as a single JSON object matching the required schema. No prose.",
            },
        ]
        schema_format = {
            "type": "json_schema",
            "json_schema": {"name": request.operation, "schema": dict(request.output_schema), "strict": True},
        }
        try:
            response = await self._create(messages=final_messages, response_format=schema_format)
        except LiveBackendError:
            try:  # endpoint rejected json_schema (gateway without support) -> prompt-JSON fallback
                response = await self._create(messages=final_messages)
            except LiveBackendError:
                return None
        self._accumulate(response, tokens)
        return _try_json_object(response.choices[0].message.content or "")


class OpenAICompatibleCodingBackend:
    """CodingBackend that authors file contents via the live model.

    Confinement is layered: the adapter writes only declared target paths
    inside the sandbox (traversal-checked), and the safety boundary still
    owns detection, authorization, and synchronization downstream.
    """

    def __init__(self, *, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def apply_task(self, request: CodingBackendRequest) -> CodingBackendResult:
        task = request.task
        sandbox = Path(request.sandbox_root)
        sandbox_resolved = sandbox.resolve()
        approved = tuple(target.path for target in task.target_paths)
        current: dict[str, str] = {}
        for path in approved:
            file_path = sandbox / path
            current[path] = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
        prompt = (
            "Apply exactly one approved build task inside the sandbox.\n"
            f"Task: {task.responsibility}\n"
            f"Expected result: {task.expected_result}\n"
            f"Approved target paths: {json.dumps(list(approved))}\n"
            f"Current file contents: {json.dumps(current, ensure_ascii=False)}\n"
            + (f"A prior attempt failed: {request.prior_error}\n" if request.prior_error else "")
            + "Return a single JSON object mapping each approved path to its complete new "
            "file content. Only approved paths. No prose."
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You edit files precisely and never touch unlisted paths."},
                    {"role": "user", "content": prompt},
                ],
            )
        except Exception as exc:
            return CodingBackendResult(
                execution_result=ExecutionResult.FAILED,
                observation=f"live API call failed: {type(exc).__name__}",
                reported_changed_paths=(),
            )
        usage = getattr(response, "usage", None)
        token_usage = (
            TokenUsage(
                input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                tool_calls=0,
            )
            if usage is not None
            else None
        )
        payload = _try_json_object(response.choices[0].message.content or "")
        if payload is None:
            return CodingBackendResult(
                execution_result=ExecutionResult.FAILED,
                observation="model returned no JSON file map",
                reported_changed_paths=(),
                usage=token_usage,
            )
        overreach = sorted(set(payload) - set(approved))
        if overreach:
            return CodingBackendResult(
                execution_result=ExecutionResult.FAILED,
                observation=f"model attempted unauthorized paths: {overreach}",
                reported_changed_paths=(),
                usage=token_usage,
            )
        written: list[str] = []
        for path in approved:
            if path not in payload:
                continue
            content = payload[path]
            if not isinstance(content, str):
                return CodingBackendResult(
                    execution_result=ExecutionResult.FAILED,
                    observation=f"content for {path!r} is not a string",
                    reported_changed_paths=tuple(written),
                    usage=token_usage,
                )
            destination = (sandbox / path).resolve()
            if sandbox_resolved not in destination.parents:
                return CodingBackendResult(
                    execution_result=ExecutionResult.FAILED,
                    observation=f"path escapes sandbox: {path!r}",
                    reported_changed_paths=tuple(written),
                    usage=token_usage,
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
            written.append(path)
        if not written:
            return CodingBackendResult(
                execution_result=ExecutionResult.FAILED,
                observation="model wrote no approved path",
                reported_changed_paths=(),
                usage=token_usage,
            )
        return CodingBackendResult(
            execution_result=ExecutionResult.COMPLETED,
            observation=f"wrote {sorted(written)}",
            reported_changed_paths=tuple(sorted(written)),
            usage=token_usage,
        )
