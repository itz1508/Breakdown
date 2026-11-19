"""Live smoke probe for an OpenAI-compatible endpoint (opt-in, never in pytest).

Set BREAKDOWN_API_BASE_URL / BREAKDOWN_API_KEY / BREAKDOWN_MODEL (see
.env.example for the Databricks and custom-gateway recipes), then:

    uv run --no-sync python scripts/live_probe.py

Exercises one structured-output round through OpenAICompatibleRoleBackend
and reports model, usage, and latency. Exit codes: 0 ok, 1 probe failed,
2 configuration missing.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path


def main() -> int:
    from breakdown.live_backend import (
        LiveBackendError,
        OpenAICompatibleRoleBackend,
        build_openai_client,
        resolve_model,
    )
    from breakdown.models import RoleBackendRequest, Settings

    settings = Settings()
    try:
        client = build_openai_client(settings)
        model = resolve_model(settings, "researcher")
    except LiveBackendError as exc:
        print(f"probe configuration error: {exc}")
        return 2
    backend = OpenAICompatibleRoleBackend(client=client, model=model, tool_root=Path("."), max_tool_rounds=2)
    request = RoleBackendRequest(
        operation="live_probe",
        system_prompt="Answer precisely with JSON only.",
        prompt='Return a JSON object {"status": "ok"} and nothing else.',
        output_schema={"type": "object", "properties": {"status": {"type": "string"}}},
        tool_names=(),
    )
    started = time.monotonic()
    try:
        response = asyncio.run(backend.generate(request))
    except LiveBackendError as exc:
        print(f"probe failed: {exc}")
        return 1
    elapsed = time.monotonic() - started
    print(f"model: {model}")
    print(f"structured_output: {response.structured_output}")
    print(
        f"usage: {response.usage.input_tokens} in / {response.usage.output_tokens} out"
        f" / {response.usage.tool_calls} tool calls"
    )
    print(f"latency: {elapsed:.2f}s")
    if response.structured_output != {"status": "ok"}:
        print("probe warning: endpoint reachable but structured output unexpected")
        return 1
    print("probe: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
