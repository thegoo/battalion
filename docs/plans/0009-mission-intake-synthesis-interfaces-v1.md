# Mission Intake Synthesis Interfaces v1 Plan

This tracked Plan records the Battalion-generated `.battalion/mission-plan.md` for Mission Intake Synthesis Interfaces v1.

## Objective

Build mission intake synthesis interfaces while preserving Battalion doctrine:

- Battalion leads with deterministic, no-AI intake by default.
- AI-assisted synthesis is explicit opt-in via `--ai-assisted-intake`.
- AI assistance is limited to mission intake and only structures raw human requirements into traceable intent.
- Deterministic cataloging, playbook matching, and Plan generation still own the authoritative Plan.
- Original mission text remains unchanged.
- Over-complex deterministic input stops clearly and recommends the AI-assisted flag instead of fabricating a Plan.

## Requirements

### R-001 Introduce Mission Intake Synthesis Interfaces

- Mission intake exposes a deterministic synthesis interface.
- The AI-assisted path routes through an explicit stub or adapter boundary without requiring a provider.
- Synthesis output records traceability to the original human requirement.
- The original mission text remains unchanged.

### R-002 Preserve Compound Documentation Artifacts

- `battalion "Create README.md and CONTRIBUTING.md"` records README.md and CONTRIBUTING.md as distinct requested artifacts.
- The generated contract includes separate deliverables or requirements for README.md and CONTRIBUTING.md.
- Questions and acceptance criteria are not README-only when multiple docs are requested.

### R-003 Add Discoverable AI-Assisted Intake Opt-In

- A CLI flag exposes AI-assisted intake as an explicit opt-in.
- The flag is visible in help and docs.
- The stub path does not call or require an AI provider.
- Plan generation remains deterministic after structured intake.

### R-004 Refuse Over-Complex Deterministic Intake

- Over-complex deterministic input exits with a clear non-destructive error.
- The error recommends rerunning with the AI-assisted intake flag.
- No misleading authoritative Plan is produced for refused deterministic input.

### R-005 Preserve Existing Command Routing

- Happy-path tests cover normal compound documentation intake and AI-assisted stub routing.
- No-argument behavior remains a clear error.
- Unsupported input, unquoted junk, reserved command collisions, and explicit subcommands preserve existing behavior.
- The full deterministic test suite passes.

## Out of Scope

- Real AI provider integration.
- AI-generated Plans.
- AI approval, implementation, or decision-making.
- Executor dispatch changes.
- Review engine changes.
- Application, API, data, or deployment behavior unrelated to intake.

## Validation

- Focused TDD covers compound docs, no-AI default behavior, AI opt-in routing, deterministic refusal, and existing CLI routing.
- Full deterministic suite must pass.
- Dogfood evidence must include the failed pre-fix behavior, the refusal path, and corrected Plan generation with `--ai-assisted-intake`.
