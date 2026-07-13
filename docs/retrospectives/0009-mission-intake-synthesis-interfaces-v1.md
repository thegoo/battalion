# Mission Intake Synthesis Interfaces v1 Retrospective

## What Changed

- Added a mission intake synthesis boundary with deterministic and AI-assisted stub implementations.
- Recorded structured intake output in the ledger without mutating the original mission prompt.
- Added compound Markdown artifact extraction so README.md and CONTRIBUTING.md remain distinct deliverables.
- Added `--ai-assisted-intake` as an explicit opt-in for bare mission intake.
- Added deterministic refusal for over-complex mission text when the no-AI path cannot structure intent confidently.
- Updated assessment and mission-contract generation for compound docs and this intake-synthesis slice.
- Updated help/docs and regression tests.

## Determinism Lesson

Determinism begins after mission intent is sufficiently understood and structured.

Before that point, deterministic behavior must either structure the mission conservatively from clear signals or stop with a clear request for better intake. It must not flatten scope just to keep generating artifacts. The README/CONTRIBUTING dogfood failure was useful because it showed a boring-looking but wrong artifact path: deterministic output can still be misleading when the intake structure is incomplete.

## Doctrine Check

- Battalion owns WHAT: structured intent and deterministic Plans remain Battalion-owned.
- Executors own HOW: no implementation strategy was delegated to intake synthesis.
- Humans own decisions: AI-assisted intake is opt-in and does not approve, decide, or implement.
- Evidence over assertion: failing tests and dogfood output drove the fix.
- Battalion remains boring: the AI path is a stub boundary, not a provider integration.

## Remaining Findings

- The AI-assisted path is intentionally a stub. A future provider must preserve the same traceability and mission-intake-only boundary.
- The over-complex heuristic is conservative and should evolve from evidence, not cleverness.
- Generated Plan wording for this slice still uses some generic CLI workflow execution-strategy language; it is adequate for this slice but should improve as intake-specific playbooks mature.
