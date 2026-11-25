# Onboarding Guide

For developers and operators setting up Breakdown for the first time.

## Context and goals

Breakdown is a Python package and CLI for running a contract-driven repository workflow. A normal run pauses at explicit user decisions, persists its state under the target repository, and resumes in a later process.

The quickest safe onboarding path is the offline demo. It uses scripted backends and does not require model API credentials. It validates local wiring and workflow behavior; it does not prove live model quality.

## Prerequisites

- Python 3.11 or newer. The project declares Python >=3.11.
- uv for locked dependency installation and command execution.
- Git is recommended for source identity and checkpoint visibility. The checkpoint implementation also has a non-Git path.
- Read access to the Breakdown repository.
- Read/write access to the target repository and permission to create its .breakdown state directory and run-scoped sandbox.
- For live mode only: network access to an OpenAI-compatible chat endpoint, an API key, a served model name, and validated BackendBinding records.
- Do not give workflow agents access to secrets or unrelated repositories. Role tools deny reads of .env files.

## Install

Clone the repository and install the locked dependencies:

    git clone https://github.com/itz1508/Breakdown.git
    cd Breakdown
    uv sync --locked

Confirm the workflow definition and generated contracts align:

    uv run --no-sync python -m breakdown --check

The project uses the Python version declared in .python-version and pyproject.toml. Development dependencies include pytest, pytest-asyncio, Ruff, mypy and PyYAML typing support.

## Configure local settings

Runtime settings are loaded by Pydantic Settings from the environment and .env, using the BREAKDOWN_ prefix. The names and examples are in .env.example.

Common settings:

| Variable | Purpose | Default |
|---|---|---|
| BREAKDOWN_WORKFLOW_PATH | Workflow definition path | breakdown.yaml |
| BREAKDOWN_TARGET_REPO | Target repository root | . |
| BREAKDOWN_STATE_ROOT | State directory under target | .breakdown |
| BREAKDOWN_BACKEND_BINDINGS_PATH | Backend binding JSON path | unset |
| BREAKDOWN_API_BASE_URL | OpenAI-compatible API base URL | unset |
| BREAKDOWN_API_KEY | API key for live backend | unset |
| BREAKDOWN_MODEL | Default served model name | unset |
| BREAKDOWN_MODEL_AUDITOR | Auditor model override | default model |
| BREAKDOWN_MODEL_RESEARCHER | Researcher model override | default model |
| BREAKDOWN_MODEL_CODER | Coder capability model override | default model |
| BREAKDOWN_MODEL_PLANNER | Planner model override | default model |
| BREAKDOWN_API_MAX_TOOL_ROUNDS | Maximum live tool rounds | 8 |

For offline-demo mode, no .env file or API credentials are required. For live mode, copy .env.example to an untracked .env and set only the values required by your endpoint. Never commit real credentials.

## First run: offline demo

From the Breakdown repository root, create a disposable target directory and start a run:

    mkdir -p demo-target
    uv run --no-sync python -m breakdown run "Create the demo change record" --workflow ./breakdown.yaml --target ./demo-target --offline-demo

The CLI prints the run ID, current state and current stage. The run normally pauses at the Research approval gate. Record the run ID, then approve and resume:

    uv run --no-sync python -m breakdown decide RUN_ID approve --workflow ./breakdown.yaml --target ./demo-target --offline-demo
    uv run --no-sync python -m breakdown resume RUN_ID --workflow ./breakdown.yaml --target ./demo-target --offline-demo

The workflow advances until the next decision or terminal state. The plan approval gate is separate; inspect the current report, make the decision shown by the application, and resume again:

    uv run --no-sync python -m breakdown status RUN_ID --target ./demo-target

Use the exact action offered by the pending decision. A model response or chat message is not an approval; decisions must be recorded with the CLI/application.

## Live endpoint setup

Live mode uses the OpenAI-compatible backend adapter. It is suitable for OpenAI, Databricks Model Serving, or a compatible gateway. Native provider-specific features are not implied.

1. Configure BREAKDOWN_API_BASE_URL, BREAKDOWN_API_KEY and BREAKDOWN_MODEL in .env.
2. Optionally set per-role model overrides.
3. Run the endpoint probe:

       uv run --no-sync python scripts/live_probe.py

4. Evaluate the candidate endpoint:

       uv run --no-sync python evals/run.py --live

5. Review the evaluation output and create BackendBinding records using the schema/example in bindings.example.json. Bindings must identify permitted operations and supported capabilities; they are validated before reaching roles.
6. Start a live run with the binding file:

       uv run --no-sync python -m breakdown run "Your request" --workflow ./breakdown.yaml --target /path/to/target --live --bindings ./bindings.json

Do not treat an endpoint smoke test or fake-backend evaluation as proof of live role quality. Live evaluation is required for the binding process described by the repository.

## Access and safety

- The target root is the boundary for repository tools.
- Tool reads of .env and .env.* are denied.
- Builder writes inside a run-scoped sandbox, not directly to the target repository.
- Runtime checks the approval binding, frozen plan, source checkpoint, preflight, task targets and changed paths before synchronization.
- State is stored under the target's .breakdown directory. Preserve it when a run is paused or needs recovery.
- Use --force-unlock only after verifying the lock owner is no longer running and the lock is stale.
