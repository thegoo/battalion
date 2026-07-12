# Mission

**Title:** Semantic Planning Fallback and Human Decision Regeneration Fidelity v1.

Fix the defect where Battalion emits deterministic but semantically irrelevant Plans when it does not understand a mission well enough, and ensure explicit structured human decisions deterministically shape regenerated Plans without manual Plan edits.

## Objective

Battalion must recognize CLI workflow missions accurately enough to generate relevant requirements, stop with an explicit insufficient-understanding outcome when a mission is too vague or unsupported, and regenerate authoritative Plans from structured human decisions with high fidelity. Deterministic output must preserve traceability without manufacturing semantic certainty.

## Doctrine and Constraints

- This Plan is the authoritative execution artifact for this defect slice.
- Battalion owns the WHAT.
- Executors own the HOW.
- Humans own decisions.
- Plans are authoritative only when grounded in assessed mission facts.
- Evidence over assertion.
- Deterministic output must not manufacture semantic certainty.
- Battalion remains boring.
- Dogfooding friction that corrupts mission intent outranks speculative roadmap work.

## Planning Status

- Open assumptions: 1
- Open risks: 1
- Unresolved human decisions: 1
- Blockers: None identified.

## Assumptions

- A-001: The existing deterministic mission analyst and playbook model remain the correct implementation surface for this fix.

## Risks

- RISK-001 [OPEN]: Tightening fallback behavior could expose existing weak mission prompts that previously received generic Plans.

## Human Decisions

- Humans decide whether the completed implementation satisfies this Plan.
- Battalion recommendations are advisory signals, not approvals.
- HD-001 [OPEN]: Decide whether the semantic fallback behavior is acceptable for PR.

## Requirements

### R-001

- Statement: Classify CLI workflow missions as a first-class mission shape.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - CLI, terminal UX, command routing, parser, argument, subcommand, and interactive workflow language classifies as CLI workflow work.
  - The exact bare-command UX mission classifies as `CLI / Workflow`.
  - The resulting Plan covers bare requirement routing, explicit subcommands, interactive assessment, structured answers, automatic initialization, Plan generation, assess compatibility, help, docs, and tests.

### R-002

- Statement: Prevent unsupported generic application requirements.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - CLI workflow Plans do not include generic application entrypoint requirements.
  - CLI workflow Plans do not include HTTP/request-response error handling language.
  - CLI workflow Plans do not include deployment-environment risks unless the mission explicitly requires deployment.
  - CLI workflow Plans do not include unrelated application boilerplate.

### R-003

- Statement: Prefer explicit insufficient-understanding outcomes over fabricated requirements.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Low-confidence unknown missions produce a clarification-required or unable-to-plan outcome.
  - Low-confidence unknown missions do not generate traceable implementation requirements.
  - No authoritative Plan is generated for insufficiently understood missions.

### R-004

- Statement: Preserve deterministic contracts without false semantic precision.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Requirement IDs remain stable and traceable when a mission is understood.
  - Unsupported missions still produce deterministic assessment artifacts.
  - Assessment reports uncertainty instead of converting vague input into generic implementation obligations.

### R-005

- Statement: Add regression coverage and dogfood evidence.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Regression tests cover the exact bare-command UX mission.
  - Regression tests cover low-confidence unknown mission fallback.
  - The full deterministic test suite passes.
  - Evidence and retrospective artifacts record the root cause, determinism lesson, and fix.

### R-006

- Statement: Regenerate Plans from structured human decisions without manual Plan edits.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Human feedback is stored as structured decision/input data and does not mutate the original mission prompt.
  - Explicit human decisions override ambiguous inferred behavior when regenerating a Plan.
  - The regenerated bare-invocation UX Plan includes the decided parser errors, reserved command behavior, assess removal, internal assessment workflow, multiline/quoted requirement support, interaction preservation, automatic initialization, Plan generation, and test requirements.
  - Missing structured decisions do not silently invent the decided strict semantics.
  - Conflicting or malformed human decision data blocks planning with clear clarification-required output.
  - The regenerated Plan excludes generic application entrypoints, HTTP/request-response security language, deployment-environment risks, unrelated application boilerplate, and compatibility language that keeps `assess` public.

## Deliverables

- Updated CLI workflow playbook and mission attribute catalog.
- Updated mission assessment and mission analyst behavior.
- Updated Plan rendering for CLI workflow Plans.
- Regression tests for CLI UX planning and insufficient-understanding fallback.
- Regression tests for structured human-decision regeneration fidelity, missing-decision behavior, conflicting decisions, and malformed decision data.
- Regenerated dogfood Plan for the bare-command UX mission.
- Evidence and retrospective artifacts for this slice.

## Out of Scope

- Implementing the bare `battalion "My requirement"` interface.
- Review engine changes.
- Evidence Report changes.
- Executor dispatch changes.
- Integrations.
- Replacing deterministic planning with model-based planning.

## Execution Strategy

1. Treat the failed bare-command UX Plan as dogfood evidence.
2. Add CLI workflow classification and attributes.
3. Generate CLI-specific mission requirements for command routing and interactive workflow changes.
4. Replace unsupported generic fallback with explicit insufficient-understanding behavior.
5. Tighten Plan rendering where CLI workflow Plans previously inherited generic application language.
6. Add regression tests for the exact dogfood mission and unknown fallback.
7. Add failing tests for structured human-decision regeneration fidelity, missing-decision behavior, conflicting decisions, and malformed decision data before implementation.
8. Implement the minimal validation and contract-generation changes needed to make those tests pass.
9. Regenerate the bare-command UX Plan from structured human decisions and inspect it for required and forbidden content.
10. Run the full deterministic test suite and record evidence.

## Validation Plan

- R-001: validate classification and generated Plan content for the exact bare-command UX mission.
- R-002: validate forbidden generic application, HTTP, deployment, and boilerplate content is absent.
- R-003: validate low-confidence unknown missions do not generate implementation requirements or an authoritative Plan.
- R-004: validate deterministic artifact structure remains stable for understood and insufficiently understood missions.
- R-005: validate regression tests, evidence, retrospective, regenerated dogfood Plan, and full test output.
- R-006: validate human decisions regenerate the strict bare-invocation Plan, missing decisions do not invent strict semantics, and malformed/conflicting decisions block planning clearly.

## Evidence Required

- Requirement evidence mapped by ID.
- Passing automated test output.
- Regenerated dogfood Plan summary.
- Human decision evidence from PR approval or merge when observed.

## Definition of Complete

- Every requirement has implementation evidence or an explicit human disposition.
- Every acceptance criterion has deterministic validation evidence or an explicit unable-to-verify finding.
- The regenerated dogfood Plan is semantically relevant, grounded in structured human decisions, and free of forbidden generic content.
- The final human decision is recorded outside Battalion recommendations.
