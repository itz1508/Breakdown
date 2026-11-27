# Structure Review — Revised Package Layout

The current implementation has five agent identities. The accepted target has six, adding Discovery as an independent package; this source branch does not yet implement or register Discovery. This document supersedes the former four-agent review and its Coder-under-Auditor ownership assumption.

## Current package rules

- Coder is a standalone package with its own `agent.py`, `SKILL.md`, and tests.
- Builder is an independent sibling at `builder/` and does not use the shared model loop.
- Every agent keeps its instructions colocated in `SKILL.md`.
- `__main__.py` is the only composition root and constructs the agent registry.
- Runtime, Storage, Tools, Safety and Memory remain system-owned capabilities.
- No root-level `agents/skills/` implementation tree or `breakdown/roles/` package is part of the target.

## Consolidation criteria

A legacy path is removable only when its behavior has a new owner, every consumer is rewired, the replacement is exercised by relevant tests, and no active import or configuration reference remains. Historical documents that describe a superseded package tree must be rewritten or removed rather than presented as current architecture.
