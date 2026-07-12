# Mission

**Title:** Dogfooding Friction Doctrine v1.

Add a concise doctrine principle stating that friction discovered through real dogfooding can outrank speculative roadmap work.

## Objective

Update Battalion doctrine so future slices prioritize dogfooding findings that block use, corrupt intent, weaken evidence, or materially increase human effort, while preserving the existing boring, evidence-driven, human-decision operating model.

## Doctrine and Constraints

- This Plan is the authoritative execution artifact for the Dogfooding Friction Doctrine v1 slice.
- Battalion owns the WHAT.
- Executors own the HOW.
- Humans own engineering decisions.
- Battalion reports facts and recommendations; recommendations are not decisions.
- Plans are authoritative execution artifacts.
- Evidence Reports compare execution artifacts against Plans.
- Battalion remains boring.
- Battalion builds Battalion using its own artifacts.
- Keep wording concise and implementation-neutral.
- Do not change roadmap sequencing, command behavior, or runtime artifact generation in this slice.

## Planning Status

- Open assumptions: 1
- Open risks: 1
- Unresolved human decisions: 1
- Blockers: None identified.

## Assumptions

- A-001: `doctrine/README.md` is the authoritative doctrine surface for this principle.

## Risks

- RISK-001 [OPEN]: The principle could be misread as permission to chase every small annoyance unless the wording explicitly distinguishes material friction from cosmetic issues.

## Human Decisions

- Humans decide whether to proceed, accept risk, defer, reject, merge, deploy, or approve the work.
- Battalion recommendations are advisory signals, not approvals.
- HD-001 [OPEN]: Decide whether the doctrine wording captures the intended dogfooding priority without broadening scope into cosmetic churn.

## Requirements

### R-001

- Statement: Add the dogfooding friction priority principle to doctrine.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - `doctrine/README.md` states that friction discovered through real dogfooding can outrank speculative roadmap work.
  - The wording says real usage findings may supersede planned roadmap sequencing when mission impact justifies it.
  - The wording preserves the distinction between material workflow friction and cosmetic issues.

### R-002

- Statement: Preserve existing Battalion doctrine boundaries.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Existing doctrine remains intact: Battalion remains boring, evidence over assertion, humans decide, Plans are authoritative, and Battalion builds Battalion using its own artifacts.
  - The new wording does not grant Battalion decision authority or implementation strategy ownership.
  - The change remains implementation-neutral.

### R-003

- Statement: Produce slice evidence and retrospective.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Evidence maps validation results to requirement IDs.
  - Retrospective records dogfooding friction found during this slice.
  - Validation includes at least documentation inspection and relevant automated tests.

### R-004

- Statement: Report current local run guidance.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Guidance confirms whether running `battalion ...` from the repository directory is correct.
  - Guidance states whether editable install and virtual environment setup are required.
  - Guidance includes minimal commands to update to latest `main` and invoke the CLI safely.

## Deliverables

- Updated `doctrine/README.md`.
- Source-controlled Plan for this doctrine slice.
- Source-controlled validation evidence.
- Source-controlled dogfooding retrospective.
- Local run instructions in the final slice report.

## Out of Scope

- Runtime command behavior changes.
- Roadmap reordering.
- Artifact lifecycle redesign.
- New CLI commands.
- Observability or integration work.
- Commit, push, PR, or merge.

## Execution Strategy

1. Start from latest `main` and create a dedicated branch.
2. Dogfood the mission with Battalion and inspect the generated Plan.
3. Add concise doctrine wording for dogfooding friction priority.
4. Record evidence and retrospective artifacts.
5. Inspect install and CLI docs to confirm local run guidance.
6. Run relevant validation and report results.

## Validation Plan

- R-001: Inspect `doctrine/README.md` for the new principle and mission-impact qualifier.
- R-002: Inspect surrounding doctrine to confirm existing principles remain intact and decision authority does not move to Battalion.
- R-003: Verify evidence and retrospective files exist and map to this slice.
- R-004: Inspect `README.md`, `pyproject.toml`, and `setup.py`; confirm the console script entry point and minimal local commands.
- Full validation: run `python -m pytest`.

## Evidence Required

- Requirement evidence mapped by ID.
- Passing automated test output or explicit unable-to-verify finding.
- Human decision evidence for final approval or merge outside Battalion recommendations.

## Definition of Complete

- Every requirement has implementation evidence or an explicit human disposition.
- Every acceptance criterion has deterministic validation evidence or an explicit unable-to-verify finding.
- The doctrine update is concise, implementation-neutral, and consistent with existing Battalion doctrine.
- The final human decision is recorded outside Battalion recommendations.
