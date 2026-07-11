# Mission

**Title:** Create Plan Review v1.

Define deterministic review of a completed implementation against the authoritative Plan.

## Objective

Create a Plan Review v1 capability that compares completed implementation evidence against the authoritative Plan and reports factual review findings without making the human decision.

## Doctrine and Constraints

- This Plan is the authoritative execution artifact for the Plan Review v1 slice.
- Battalion owns the WHAT.
- Executors own the HOW.
- Battalion reports facts and may record recommendations.
- Recommendations are not decisions.
- Humans own engineering decisions.
- The Plan is the source contract for review.
- Evidence Reports compare execution artifacts against Plans, but Evidence Report v1 is out of scope for this slice.
- Battalion remains boring.
- Battalion builds Battalion using its own artifacts.
- Keep scope limited to deterministic comparison of completed implementation evidence against the authoritative Plan.
- Preserve deterministic, source-controlled, human-readable artifacts.

## Planning Status

- Open assumptions: 2
- Open risks: 2
- Unresolved human decisions: 2
- Blockers: Plan Template v1 PR must be merged and the human must explicitly confirm the merge before implementation begins.

## Assumptions

- A-001: Plan Review v1 can consume the authoritative Plan from `.battalion/mission-plan.md`.
- A-002: Implementation evidence will be available as source-controlled files, command output, runtime observations, or explicit unable-to-verify findings.

## Risks

- RISK-001 [OPEN]: Review output could drift into approval language if findings and human decisions are not kept separate.
- RISK-002 [OPEN]: Review may become too broad if it tries to generate Evidence Reports, select executors, or gate execution in this slice.

## Human Decisions

- Humans decide whether to proceed, accept risk, defer, reject, merge, deploy, or approve the work.
- Battalion recommendations are advisory signals, not approvals.
- HD-001 [OPEN]: Confirm that the Plan Template v1 PR has merged before Plan Review v1 implementation begins.
- HD-002 [OPEN]: Approve the final Plan Review v1 output shape before treating it as canonical review input for human decisions.

## Requirements

### R-001

- Statement: Compare completed implementation against the authoritative Plan.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Plan Review v1 reads or is provided the authoritative Plan for the completed slice.
  - Plan Review v1 identifies the Plan requirements and acceptance criteria being reviewed.
  - Plan Review v1 does not review work that is outside the supplied Plan unless it records that work as out-of-scope evidence.
- Source: Plan Review v1 must define deterministic review of a completed implementation against the authoritative Plan.

### R-002

- Statement: Report only the five doctrine-approved review questions.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Review output answers: What did the Plan require?
  - Review output answers: What evidence exists?
  - Review output answers: What matches?
  - Review output answers: What does not match?
  - Review output answers: What could not be verified?
- Source: The next slice must answer only the five specified comparison questions.

### R-003

- Statement: Preserve human authority in review output.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Review output may report facts and recommendations.
  - Review output does not approve, reject, merge, deploy, authorize execution, or make the human decision.
  - Review output clearly separates findings, recommendations, and human decision inputs.
- Source: Battalion reports facts and recommendations; humans decide.

### R-004

- Statement: Keep Plan Review v1 narrowly scoped.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - The slice does not implement Evidence Report v1.
  - The slice does not implement skills, integrations, catalog migration, executor changes, or autonomous gating.
  - The slice does not begin until Plan Template v1 is merged and the human explicitly confirms the merge.
- Source: Next-slice planning request excludes Evidence Report v1, skills, integrations, catalog migration, executor changes, and autonomous gating.

### R-005

- Statement: Cover Plan Review v1 with deterministic validation.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Tests or deterministic fixtures cover matching evidence.
  - Tests or deterministic fixtures cover non-matching evidence.
  - Tests or deterministic fixtures cover unable-to-verify findings.
  - Tests assert that approval, rejection, merge, deploy, and autonomous gating language is not emitted as a decision.
  - The full deterministic test suite passes.
- Source: Plan Review v1 must be deterministic and preserve human authority.

## Deliverables

- Deterministic Plan Review v1 implementation surface.
- Review output format that answers only the five approved comparison questions.
- Tests or fixtures covering match, mismatch, unable-to-verify, and human-authority boundaries.
- Documentation describing Plan Review v1 as factual review input for human decisions.
- Validation evidence mapped to requirement IDs.

## Out of Scope

- Evidence Report v1.
- Skills.
- Integrations.
- Catalog migration.
- Executor changes.
- Autonomous gating.
- Approval, rejection, merge, deploy, or execution authority.
- Any Plan Review v1 implementation work before the Plan Template v1 PR is merged and the human explicitly confirms the merge.

## Execution Strategy

1. Wait for human confirmation that the Plan Template v1 PR has merged.
2. Define the minimal Plan Review v1 input and output contract around the five approved review questions.
3. Implement deterministic extraction or mapping from the authoritative Plan requirements to review findings.
4. Add fixtures or tests for matching evidence, non-matching evidence, and unable-to-verify evidence.
5. Add tests that prevent review output from making approval, merge, deploy, or autonomous gate decisions.
6. Document the Plan Review v1 review boundary and human-decision handoff.
7. Run the full deterministic test suite and record validation evidence.

## Validation Plan

- Deterministic validation must prove each requirement by ID or report that it is unable to verify it.
- R-001: validate that review input is compared against the authoritative Plan requirements.
- R-002: validate that output answers only the five approved review questions.
- R-003: validate that findings and recommendations remain separate from human decisions.
- R-004: validate that out-of-scope systems and autonomous gating are not introduced.
- R-005: validate match, mismatch, unable-to-verify, and authority-boundary test coverage.

## Evidence Required

- Requirement evidence mapped by ID.
- Passing automated test output.
- Review output examples or fixtures for match, mismatch, and unable-to-verify cases.
- Human decision record confirming Plan Template v1 merge before implementation begins.

## Definition of Complete

- Every traceable requirement has implementation evidence or an explicit human disposition.
- Every acceptance criterion has deterministic validation evidence or an explicit unable-to-verify finding.
- Plan Review v1 reports facts, findings, and recommendations without making the human decision.
- Human decisions listed in this Plan are completed, rejected, superseded, deferred, or accepted with risk by humans.
- The final human decision is recorded outside Battalion recommendations.
