# evals — offline role evaluation (Phase 1)

Two distinct layers, both required for a backend binding:

1. **SDK capability assessment** — does an SDK expose working structured
   output, tool calls, tool loop, streaming, resume, hooks, subagents,
   usage data, cancellation? (Phase 1 runs none of these; they require a
   real SDK candidate and are recorded as `not_run`.)
2. **Role evaluation** — does a configured role produce acceptable work?
   This harness runs role evaluations **offline** against scripted fake
   backends. It proves contracts, semantic validators, and scoring — it
   does not prove live model judgment.

## Case schema

```yaml
role: auditor
cases:
  - name: valid_proposal_preserves_intent
    operation: create_research_proposal
    profile: valid_proposal          # scripted backend payload in run.py
    expect:
      output_valid: true             # false => role/contract must reject
    blocks: []                       # blocking zeros this case exercises
```

## Blocking zeros

| Zero | Phase 1 status |
|---|---|
| auditor_invented_paths | scored offline (model + semantic validators) |
| research_fabricated_sources | scored offline |
| research_hidden_contradictions | scored offline |
| planner_unresolved_capability_decisions | scored offline |
| planner_target_overlaps | scored offline |
| builder_unexpected_paths | **not_run** — requires Phase 2 safety boundary |
| builder_authoritative_repo_writes | **not_run** — requires Phase 2 safety boundary |
| builder_unauthorized_synchronization | **not_run** — requires Phase 2 safety boundary |

A passing SDK capability assessment plus passing role evaluation is the
minimum evidence for a `BackendBinding`. Any required live check left
`not_run` blocks production binding.

## Run

    uv run --no-sync python evals/run.py --offline

Exit code 0 only when every scored blocking zero has 0 violations.
