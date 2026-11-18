# AGENTS.md — core rules (human-owned; agents cannot edit this file)

Keep this file short. It is read on every run. The living plan lives in
`PLANS.md`; runtime records live in `.breakdown/`.

## Rules
1. Follow `breakdown.yaml` stage by stage. Never skip a stage because a similar earlier run exists.
2. Create or change only paths in the approved ImplementationPlan. A needed path that is not in the plan means STOP and report; newly required paths return `uncertainty` to Planning.
3. Reuse an existing SDK or standard-library capability before proposing custom code. Record evidence and classify coverage: `covered`, `partial`, `not_covered`, `uncertainty`.
4. `uncertainty` never advances a stage or a gate. Lifecycle `failed` is never recorded as criterion `not_valid` — they are distinct concepts.
5. Workflow-execution agents may not read `.env`, dump the environment, or edit `AGENTS.md`, `breakdown.yaml`, `PLANS.md`, or `.breakdown/`. (Repository maintenance by the owner or their coding agent updates `PLANS.md` under the ExecPlan discipline — that is not a workflow run.)
6. A model statement or chat text is never user approval. Only an explicit recorded decision (`approve`) grants authority to advance.
7. Role processors never invoke the next workflow role directly; contracts activate roles and the runtime owns progression.
8. Builder works only inside the sandbox. Runtime alone authorizes synchronization, and only approved paths copy back.

## Good case
Task target paths are `src/util.py` and `tests/test_util.py` (one cohesive change).
Builder edits both inside the sandbox; checks pass; Runtime independently detects
exactly those changed paths and authorizes synchronization of only those paths.

## Bad case
Task target is `src/util.py`. Builder also creates `src/util_helpers.py` "to keep
things tidy". Changed-path detection marks it unexpected (`not_valid`); all
synchronization is blocked.
