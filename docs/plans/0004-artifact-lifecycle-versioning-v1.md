# Mission

**Title:** Artifact Lifecycle and Versioning v1.

Define Battalion doctrine for artifact lifecycle states and versioning without introducing runtime resolver, manifest, schema, or folder migration behavior.

## Objective

Update doctrine so Battalion artifacts have concise lifecycle and versioning rules: Draft, Approved, Completed, Superseded; latest non-superseded version is authoritative; older versions remain traceable history.

## Doctrine and Constraints

- This Plan is the authoritative execution artifact for the Artifact Lifecycle and Versioning v1 slice.
- Battalion owns the WHAT.
- Executors own the HOW.
- Battalion reports facts and may record recommendations.
- Recommendations are not decisions.
- Humans own engineering decisions.
- Plans are authoritative execution artifacts.
- Battalion remains boring.
- Battalion builds Battalion using its own artifacts.
- Keep this slice implementation-neutral and doctrinal.
- Do not design or implement a manifest, mission-record schema, folder migration, runtime resolver, catalog migration, or Evidence Report behavior.

## Planning Status

- Open assumptions: 1
- Open risks: 1
- Unresolved human decisions: 1
- Blockers: None identified.

## Assumptions

- A-001: Doctrine and roadmap wording are sufficient for this slice; runtime behavior can consume lifecycle rules in later slices.

## Risks

- RISK-001 [OPEN]: Over-specifying lifecycle mechanics could prematurely constrain future artifact storage and resolver design.

## Human Decisions

- Humans decide whether to proceed, accept risk, defer, reject, or approve the work.
- Battalion recommendations are advisory signals, not approvals.
- Human decisions must have deterministic evidence, but manual Plan or evidence edits are not the default completion mechanism.
- PR approval may satisfy human review evidence when observed.
- PR merge may satisfy authorization or completion evidence when observed.
- Manual artifact updates remain an optional fallback for workflows without a PR.
- Passing tests, implementation completion, and Battalion recommendations must never be inferred as human approval.
- HD-001 [APPROVED]: Human requested this doctrine slice and explicitly approved the lifecycle/versioning direction in discussion.

## Requirements

### R-001

- Statement: Define artifact lifecycle states in doctrine.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Doctrine lists Draft, Approved, Completed, and Superseded.
  - Doctrine defines Completed as the artifact fulfilling its role in the mission lifecycle.
  - Doctrine defines Superseded as a newer authoritative version existing.
  - Doctrine avoids Archived as the normal terminal state for completed artifacts.

### R-002

- Statement: Define artifact versioning and source-of-truth rules.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Doctrine says material artifact updates should create new versions rather than overwrite history.
  - Doctrine says material updates should, in principle, flow through assessment, plan, implementation, evidence, review, and human decision again.
  - Doctrine says the latest non-superseded version is the source of truth.
  - Doctrine says older versions remain part of the traceable historical record.

### R-003

- Statement: Preserve ADR-like supersession semantics without implementation design.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Doctrine preserves prior rationale, evidence, and human decisions as historical records.
  - The slice does not introduce a manifest, mission-record schema, folder migration, runtime resolver, catalog migration, or Evidence Report implementation.

### R-004

- Statement: Keep directly related roadmap documentation consistent.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Roadmap no longer identifies Plan Template v1 as the immediate authorized slice.
  - Roadmap versioning posture does not contradict doctrine source-of-truth rules.

### R-005

- Statement: Validate the slice deterministically and record dogfooding evidence.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Evidence maps changes to requirement IDs.
  - Retrospective records dogfooding friction and recommendations.
  - The full deterministic test suite is run or any inability to run it is recorded.

## Deliverables

- Updated `doctrine/README.md`.
- Updated `docs/ROADMAP.md` if needed to avoid contradiction.
- Dogfooded Plan artifact for this slice.
- Validation evidence mapped to requirement IDs.
- Concise dogfooding retrospective.

## Out of Scope

- Runtime resolver changes.
- Mission-record schema design.
- Manifest design.
- Folder migration.
- Artifact catalog migration.
- Evidence Report v1 implementation.
- Plan Review behavior changes.
- Commit, push, pull request, or merge work unless explicitly authorized later.

## Execution Strategy

1. Dogfood the slice by creating this authoritative Plan first.
2. Add concise artifact lifecycle and versioning doctrine.
3. Update only directly related roadmap wording needed to avoid contradiction.
4. Avoid runtime, schema, manifest, catalog, resolver, and folder migration design.
5. Produce requirement-mapped evidence and a retrospective.
6. Run the full deterministic test suite and record results.

## Validation Plan

- R-001: inspect doctrine lifecycle wording.
- R-002: inspect doctrine versioning and source-of-truth wording.
- R-003: inspect diff for absence of implementation design or runtime behavior.
- R-004: inspect roadmap wording for consistency.
- R-005: confirm evidence, retrospective, and test output exist.

## Evidence Required

- Requirement evidence mapped by ID.
- Passing automated test output or explicit unable-to-run finding.
- Human decision evidence for final PR approval or merge when this slice is reviewed.

## Definition of Complete

- Every traceable requirement has implementation evidence or an explicit human disposition.
- Every acceptance criterion has deterministic validation evidence or an explicit unable-to-verify finding.
- The doctrine remains concise, boring, and implementation-neutral.
- The final human decision is recorded outside Battalion recommendations.
