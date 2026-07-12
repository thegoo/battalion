# Mission

**Title:** Human Decision UX v1.

Remove the requirement for humans to manually edit Battalion evidence or Plan artifacts when pull request approval or merge already provides deterministic human-decision evidence.

## Objective

Make Battalion Plan and Plan Review UX report PR approval, PR merge, and manual fallback decision sources without approving, merging, or making human decisions.

## Doctrine and Constraints

- This Plan is the authoritative execution artifact for the Human Decision UX v1 slice.
- Battalion owns the WHAT.
- Executors own the HOW.
- Battalion reports facts and may record recommendations.
- Recommendations are not decisions.
- Humans own engineering decisions.
- Human decisions must be explicit and deterministically observable.
- Battalion remains boring.
- Battalion builds Battalion using its own artifacts.
- Keep this slice limited to local CLI, docs, tests, evidence, and retrospective updates.

## Planning Status

- Open assumptions: 1
- Open risks: 1
- Unresolved human decisions: 1
- Blockers: None identified.

## Assumptions

- A-001: Structured CLI input is sufficient for Human Decision UX v1; automatic GitHub API inspection is out of scope.

## Risks

- RISK-001 [OPEN]: Decision-source reporting could be mistaken for Battalion approval unless output explicitly preserves human authority.

## Human Decisions

- Humans decide whether to proceed, accept risk, defer, reject, merge, deploy, or approve the work.
- Battalion recommendations are advisory signals, not approvals.
- Human decisions must have deterministic evidence, but manual Plan or evidence edits are not the default completion mechanism.
- PR approval may satisfy human review evidence when observed.
- PR merge may satisfy authorization or completion evidence when observed.
- Manual artifact updates remain an optional fallback for workflows without a PR.
- Passing tests, implementation completion, and Battalion recommendations must never be inferred as human approval.
- HD-001 [APPROVED]: Human requested this focused slice after identifying manual evidence-document approval updates as unwanted ceremony.

## Requirements

### R-001

- Statement: Preserve explicit Human Decisions without requiring manual artifact edits by default.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Plan language states that manual Plan or evidence edits are not the default completion mechanism.
  - Plan language keeps manual artifact updates as an optional fallback for workflows without a PR.
  - Plan language states that PR approval and PR merge may satisfy deterministic human-decision evidence.

### R-002

- Statement: Report observed decision source and status in Plan Review output.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - `battalion review` accepts deterministic human decision evidence for PR approval.
  - `battalion review` accepts deterministic human decision evidence for PR merge.
  - Plan Review Markdown, JSON, and CLI output report the observed decision source and status.
  - Manual artifact updates render as an optional fallback when no PR decision evidence is supplied.

### R-003

- Statement: Preserve human authority and prevent false approval inference.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Output states that passing tests are not human approval.
  - Output states that implementation completion is not human approval.
  - Output states that Battalion recommendations are not human approval.
  - Plan Review does not approve, reject, merge, deploy, authorize execution, or make the human decision.

### R-004

- Statement: Document the Human Decision UX v1 workflow.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - README documents PR approval, PR merge, and manual fallback decision sources.
  - README does not instruct users to manually edit review or evidence artifacts when PR approval or merge is the configured source.

### R-005

- Statement: Validate the slice deterministically.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Regression tests cover PR approval decision evidence.
  - Regression tests cover PR merge decision evidence.
  - Regression tests cover manual artifact fallback semantics.
  - Regression tests cover Plan language for human-decision evidence sources.
  - The full deterministic test suite passes.

## Deliverables

- Updated Plan Template v1 human-decision and evidence language.
- Updated Plan Review decision-source reporting.
- Updated README Human Decision UX documentation.
- Regression tests for decision-source semantics.
- Validation evidence mapped to requirement IDs.
- Concise dogfooding retrospective.

## Out of Scope

- Autonomous GitHub actions.
- Automatic PR approval or merge detection through a remote API.
- Automatic merging.
- Evidence Report v1 redesign.
- Broad integrations.
- Unrelated workflow changes.
- Commit, push, merge, or pull request work unless explicitly authorized.

## Execution Strategy

1. Update this Plan first to define the Human Decision UX v1 contract.
2. Update Plan Review to accept and report deterministic decision-source evidence.
3. Update Plan Template language so manual artifact edits are not the default decision mechanism.
4. Update documentation with PR approval, PR merge, and manual fallback examples.
5. Add deterministic regression tests for PR decision evidence, manual fallback, and false approval inference.
6. Produce mapped validation evidence and a dogfooding retrospective.
7. Run the full deterministic test suite.

## Validation Plan

- R-001: validate generated Plan language for PR decision evidence and manual fallback semantics.
- R-002: validate Plan Review Markdown, JSON, and CLI output for observed decision sources and statuses.
- R-003: validate output does not infer approval from tests, implementation completion, or Battalion recommendations.
- R-004: validate README documents the intended workflow.
- R-005: run the full deterministic test suite.

## Evidence Required

- Requirement evidence mapped by ID.
- Passing automated test output.
- Human decision evidence for final PR approval or merge when this slice is reviewed.

## Definition of Complete

- Every traceable requirement has implementation evidence or an explicit human disposition.
- Every acceptance criterion has deterministic validation evidence or an explicit unable-to-verify finding.
- Human decisions listed in this Plan have deterministic evidence from PR approval, PR merge, or an explicit manual fallback record.
- The final human decision is recorded outside Battalion recommendations.
