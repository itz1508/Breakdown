# Operations

## Authority

Runtime owns the execution lifecycle, state transitions, user-decision binding, authorization and source effects. Agents return bounded results and evidence. Builder cannot authorize synchronization, and its own validation report is not independent verification.

## Safe execution boundaries

- Do not treat chat text or a model response as user approval.
- Approval must bind the exact reviewed package revision and source checkpoint.
- Builder operates only in the authorized sandbox and may change only confirmed paths.
- Runtime independently inspects exported changes before authorizing any synchronization.
- Independent verification evaluates the exported result separately from Builder.
- Completion and retention preserve evidence, unresolved items and the actual outcome.

## Evidence handling

Record exact commands and observed outputs. A command that was not executed is `not_run`. Preserve contradictions and uncertainty rather than converting them into unsupported conclusions. Do not claim a live provider, sandbox, browser, or external service was verified by offline tests.

## Ownership

Runtime orchestration is under `breakdown/system/runtime/`; persistence is under `system/storage/`; canonical tools are under `system/tools/`; safety and memory are `system/safety.py` and `system/memory.py`. Keep one owner per responsibility.
