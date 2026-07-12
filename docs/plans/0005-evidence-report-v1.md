# Mission

**Title:** Evidence Report v1.

Implement Evidence Report v1 as the decision-support artifact that consumes Plan Review output.

## Objective

Make Battalion generate deterministic Markdown and JSON Evidence Reports from Plan Review output, preserving facts, advisory recommendations, lineage metadata, and human decision boundaries.

## Doctrine and Constraints

- This Plan is the authoritative execution artifact for the Evidence Report v1 slice.
- Battalion owns the WHAT.
- Executors own the HOW.
- Battalion reports facts and may record recommendations.
- Recommendations are not decisions.
- Humans own engineering decisions.
- Evidence Reports compare execution artifacts against Plans.
- Evidence Reports support human decisions; they do not approve, reject, merge, deploy, authorize execution, or gate work.
- Battalion remains boring.
- Battalion builds Battalion using its own artifacts.
- Keep this slice limited to local CLI, deterministic artifacts, docs, tests, evidence, and retrospective updates.
- Do not build GitHub API integration, automatic approval or merge detection, artifact catalogs, runtime resolvers, dashboards, skills, integrations, autonomous gating, or Plan Review rewrites.

## Planning Status

- Open assumptions: 1
- Open risks: 1
- Unresolved human decisions: 1
- Blockers: None identified.

## Assumptions

- A-001: Consuming `.battalion/plan-review.json` is sufficient for Evidence Report v1; direct Plan Review generation or artifact resolution can remain outside this slice.

## Risks

- RISK-001 [OPEN]: Evidence Report synthesis could duplicate Plan Review or imply approval unless output is concise and explicitly advisory.

## Human Decisions

- Humans decide whether to proceed, accept risk, defer, reject, merge, deploy, or approve the work.
- Battalion recommendations are advisory signals, not approvals.
- Human decisions must have deterministic evidence, but manual Plan or evidence edits are not the default completion mechanism.
- PR approval may satisfy human review evidence when observed.
- PR merge may satisfy authorization or completion evidence when observed.
- Manual artifact updates remain an optional fallback for workflows without a PR.
- Passing tests, implementation completion, and Battalion recommendations must never be inferred as human approval.
- HD-001 [OPEN]: Decide whether Evidence Report v1 is ready to become the canonical decision-support artifact after review.

## Requirements

### R-001

- Statement: Generate deterministic Evidence Report artifacts from Plan Review output.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - `battalion evidence-report` reads `.battalion/plan-review.json` by default.
  - The command writes `.battalion/evidence-report.md`.
  - The command writes `.battalion/evidence-report.json`.
  - Output is deterministic for the same Plan Review input.

### R-002

- Statement: Summarize Plan Review findings for human decision support.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - The report identifies the mission or Plan evaluated.
  - The report identifies the Plan Review artifact consumed.
  - The report summarizes verified findings.
  - The report summarizes failed findings.
  - The report summarizes unable-to-verify findings.
  - The report summarizes out-of-scope evidence as deviations.

### R-003

- Statement: Preserve artifact lifecycle, version, and lineage metadata.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Markdown and JSON include Evidence Report schema version.
  - Markdown and JSON include artifact version.
  - Markdown and JSON include lifecycle status.
  - Markdown and JSON identify the Plan version evaluated when available.
  - Markdown and JSON identify the Plan Review version consumed.
  - Output states that the latest non-superseded Evidence Report is authoritative without implementing a resolver.

### R-004

- Statement: Preserve human decision authority.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - The report includes an explicit human-decision boundary.
  - The report includes only advisory Battalion recommendations.
  - The report does not approve, reject, merge, deploy, authorize execution, gate work, or infer human approval from tests or implementation completion.
  - The report carries observed human decision evidence from Plan Review output when present.

### R-005

- Statement: Document and validate Evidence Report v1.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - README documents `battalion evidence-report`.
  - Regression tests cover successful report generation.
  - Regression tests cover failed and unable-to-verify findings.
  - Regression tests cover lineage and human-authority language.
  - Evidence and retrospective artifacts are produced.
  - The full deterministic test suite passes.

## Deliverables

- Evidence Report v1 implementation.
- CLI command for generating Evidence Report v1.
- Updated README documentation.
- Regression tests for report generation, lineage, findings, deviations, and human-decision boundaries.
- Dogfooded Plan artifact for this slice.
- Validation evidence mapped to requirement IDs.
- Concise dogfooding retrospective.

## Out of Scope

- GitHub API integration.
- Automatic PR approval detection.
- Automatic merge detection.
- Artifact catalogs.
- Runtime artifact resolver.
- Dashboard or UI work.
- Skill layer or integrations.
- Autonomous gating.
- Plan Review logic rewrite.
- Commit, push, pull request, or merge work unless explicitly authorized later.

## Execution Strategy

1. Create this authoritative Plan before implementation.
2. Add a small Evidence Report module that consumes existing Plan Review JSON.
3. Add a CLI command that writes deterministic Markdown and JSON local runtime artifacts.
4. Include version, lifecycle, lineage, finding summary, deviations, recommendations, and human-decision boundary in both outputs.
5. Document the command and artifact boundaries.
6. Add focused regression tests.
7. Produce mapped validation evidence and a dogfooding retrospective.
8. Run the full deterministic test suite.

## Validation Plan

- R-001: generate Evidence Report artifacts from Plan Review JSON and compare repeated output.
- R-002: inspect Markdown and JSON summaries for verified, failed, unable-to-verify, and out-of-scope evidence sections.
- R-003: inspect Markdown and JSON lineage and lifecycle metadata.
- R-004: inspect Markdown and JSON authority-boundary and advisory recommendation language.
- R-005: confirm README, regression tests, evidence, retrospective, and full test output exist.

## Evidence Required

- Requirement evidence mapped by ID.
- Passing automated test output or explicit unable-to-run finding.
- Human decision evidence for final PR approval or merge when this slice is reviewed.

## Definition of Complete

- Every traceable requirement has implementation evidence or an explicit human disposition.
- Every acceptance criterion has deterministic validation evidence or an explicit unable-to-verify finding.
- Evidence Report v1 consumes Plan Review output without reimplementing Plan Review.
- The final human decision is recorded outside Battalion recommendations.
