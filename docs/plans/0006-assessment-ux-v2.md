# Mission

**Title:** Assessment UX v2 - Intent-first CLI.

Make `battalion assess "My requirement"` the single first-run command for mission intake, required human answers, assessment completion, and authoritative Plan generation.

## Objective

Replace the exposed `init -> assess -> clarify -> assess -> plan` first-run workflow with one intent-first command:

```bash
battalion assess "My requirement"
```

The command must initialize mission state when needed, ask required human questions interactively in the same run, complete assessment, and generate `.battalion/mission-plan.md`.

## Doctrine and Constraints

- This Plan is the authoritative execution artifact for the Assessment UX v2 slice.
- Battalion owns the WHAT.
- Executors own the HOW.
- Battalion asks only for human decisions it cannot make.
- Humans own answers and engineering decisions.
- Battalion reports facts and recommendations; recommendations are not decisions.
- Plans are authoritative execution artifacts.
- Battalion remains boring.
- Battalion builds Battalion using its own artifacts.
- Keep the implementation narrowly focused on first-run assessment UX.

## Planning Status

- Open assumptions: 2
- Open risks: 1
- Unresolved human decisions: 1
- Blockers: None identified.

## Assumptions

- A-001: Existing internal workspace initialization and clarification reconciliation can remain as implementation details.
- A-002: `battalion plan` may remain available for manual regeneration and legacy/internal requirement entry, but it is not the first-run workflow.

## Risks

- RISK-001 [OPEN]: Removing public `init` and `clarify` could break old user habits, but preserving them would keep the confusing UX that blocked dogfooding.

## Human Decisions

- Humans decide whether to proceed, accept risk, defer, reject, merge, deploy, or approve the work.
- Battalion recommendations are advisory signals, not approvals.
- HD-001 [APPROVED]: Prefer the intent-first UX even if old `init` and `clarify` public commands are removed.
- HD-002 [OPEN]: Decide whether the completed UX is ready for PR after review.

## Requirements

### R-001

- Statement: Make `battalion assess "My requirement"` the first-run command.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - The command creates `.battalion` mission state when none exists.
  - Long inline requirements are treated as text and do not crash path detection.
  - The command writes assessment artifacts.
  - The command generates `.battalion/mission-plan.md` when assessment is complete.

### R-002

- Statement: Capture required human answers interactively during assessment.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Assessment prompts by default when questions are required and stdin is interactive.
  - Questions are shown as `Question 1 of N`.
  - The human does not need to enter Q-IDs.
  - Answers are persisted through the existing audited clarification model where applicable.
  - Assessment reruns after answers are captured.

### R-003

- Statement: Support omitted inline requirements with a single prompt.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - `battalion assess` prompts once for the requirement when no mission exists and stdin is interactive.
  - Non-interactive use without an existing mission fails with actionable guidance.

### R-004

- Statement: Enforce the governing maximum of five questions per assessment run.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - Requirement-level questions and contract clarification questions share one five-question budget.
  - The CLI does not present `Question 6 of ...` in a single assessment run.

### R-005

- Statement: Remove old first-run command paths from public UX.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - `init` is not present in public CLI help or command routing.
  - `clarify` is not present in public CLI help or command routing.
  - README no longer presents `init` or `clarify` as supported user journeys.
  - Hidden/internal compatibility does not preserve confusing Q-ID UX as the primary path.

### R-006

- Statement: Document and validate Assessment UX v2.
- Status: proposed
- Priority: Required
- Acceptance Criteria:
  - README documents the intent-first assessment flow.
  - Regression tests cover zero-question inline assessment.
  - Regression tests cover multiple interactive questions in one run.
  - Regression tests cover omitted requirement prompting.
  - Regression tests cover automatic initialization.
  - Regression tests cover Plan generation at the end of assessment.
  - Regression tests cover old command removal.
  - Evidence and retrospective artifacts are produced.
  - The full deterministic test suite passes.

## Deliverables

- Updated assessment CLI routing and command behavior.
- Updated README first-run workflow documentation.
- Regression tests for the new assessment UX and removed public commands.
- Dogfooding evidence mapped to requirement IDs.
- Concise retrospective focused on first-run friction.

## Out of Scope

- Executor orchestration.
- Review or Evidence Report redesign.
- GitHub integration.
- Broad command renaming beyond this workflow.
- Autonomous decisions.
- Unrelated CLI cleanup.

## Execution Strategy

1. Generate this dogfood Plan before implementation and record first-run friction.
2. Keep internal initialization and clarification reconciliation where useful, but remove old public commands.
3. Change `assess` to accept positional requirement text or a file path.
4. Add prompt-on-empty behavior for first-run interactive use.
5. Add default interactive question handling with ordinal numbering and no required Q-ID input.
6. Generate the authoritative Plan automatically after successful assessment.
7. Update docs and tests.
8. Run the full deterministic test suite.

## Validation Plan

- R-001: CLI tests verify inline assessment initializes state, writes assessment artifacts, and writes `.battalion/mission-plan.md`.
- R-002: CLI tests verify ordinal interactive questions, answer persistence, re-assessment, and absence of required Q-ID UX.
- R-003: CLI tests verify omitted requirement prompting and non-interactive guidance.
- R-004: CLI tests verify the five-question cap across question sources.
- R-005: CLI tests and README inspection verify `init` and `clarify` are no longer public workflows.
- R-006: Full test suite verifies existing Battalion behavior remains intact.

## Evidence Required

- Requirement evidence mapped by ID.
- Passing automated test output.
- Human decision evidence for final PR approval or merge when this slice is reviewed.

## Definition of Complete

- Every requirement has implementation evidence or an explicit human disposition.
- Every acceptance criterion has deterministic validation evidence or an explicit unable-to-verify finding.
- First-run Battalion usage can begin with `battalion assess "My requirement"` and proceed to an authoritative Plan without manual `init`, `clarify`, or `plan` steps.
- The final human decision is recorded outside Battalion recommendations.
