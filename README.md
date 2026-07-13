# Battalion

Battalion is a deterministic engineering planning and evidence system.

It turns mission context into an authoritative objective plan, supports executor or human implementation handoff, and verifies completed work through evidence reports.

Battalion is designed around Doctrine v1.0:

- Battalion owns the WHAT.
- Executors own the HOW.
- Battalion reports facts.
- Humans make engineering decisions.
- Plans are authoritative execution artifacts.
- Evidence Reports compare execution artifacts against Plans.
- Battalion remains boring.
- Battalion eats its own dogfood.

Battalion does not call LLM APIs, choose models, configure executors, deploy systems, merge code, or approve work by assertion. It coordinates mission context, planning artifacts, and evidence.

See [doctrine/README.md](doctrine/README.md) for the current doctrine.

## Installation

Battalion requires Python 3.9 or newer.

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
battalion --help
```

Run tests from the same Python environment:

```bash
python -m pytest
```

Use `python -m pytest` instead of a globally installed `pytest` executable so the test runner uses the environment where Battalion and its dependencies were installed.

## Versioning

Battalion is pre-v1 software. Current releases use `0.x.y` versioning:

- `0.MINOR.0` may introduce product workflow changes, command behavior changes, or artifact contract refinements.
- `0.x.PATCH` is reserved for compatible fixes, documentation updates, and reliability improvements.
- `1.0.0` will mark the first stable public workflow and artifact contract.

Before v1, users should read the changelog before upgrading between minor versions.

## Core workflow

The primary workflow is:

```bash
battalion "Describe the mission"
battalion dispatch --executor codex
battalion assure
battalion report
```

`battalion "Describe the mission"` initializes mission state when needed, asks any required human questions in the same run, writes assessment artifacts, and generates the authoritative Plan. Use `battalion assure` after implementation evidence and reviews exist.

## Repository structure

Battalion is organized around Doctrine v1.0 concepts:

```text
doctrine/        Product doctrine and operating principles.
playbooks/       Mission playbook documentation and future external playbook assets.
templates/       Artifact template documentation and future template assets.
review-signals/  Review-signal documentation and future signal catalogs.
skills/          Human/executor skill guidance and future reusable skill assets.
docs/            Product and contributor documentation.
src/             Reserved future source-layout target.
battalion/       Current Python runtime package.
examples/        Example Battalion mission workspaces.
tests/           Deterministic regression tests.
```

The top-level concept directories are architectural intent and documentation surfaces. They are not current runtime package boundaries, import roots, or catalog search paths unless explicitly documented.

Additional documentation:

- [Objective Plan / Roadmap](docs/ROADMAP.md)
- [Repository Structure](docs/repository-structure.md)
- [Development Workflow](docs/development-workflow.md)

## Mission workspace

Battalion stores mission state in a `.battalion` directory inside the current working directory.

```text
.battalion/
  mission.yaml
  ledger.yaml
  agents.yaml
  attributes.yml
  assessment.json
  assessment.md
  mission-plan.md
  assignments.yaml
  dispatches/
  reports/
  events.jsonl
```

Every command locates `.battalion` relative to the current directory. The source repository root, `PYTHONPATH`, shell aliases, and manual imports are not required after installation.

Battalion artifacts are serialized truthfully:

- `.yaml` files are proper YAML.
- `.json` files are proper JSON.
- `.jsonl` files are JSON Lines.

Multiline YAML values, such as mission requirements, are written as readable block scalars.

## Commands

### `battalion "Describe the mission"`

Evaluates whether Battalion understands the mission well enough to create a reliable execution plan, then generates the authoritative Plan when assessment is complete.

```bash
battalion "Create an API endpoint to retrieve customer email."
```

You can also provide a requirement from a file:

```bash
battalion ./story.md
```

For this workflow, Battalion treats the operator input as a requirement, not a prompt. If the current directory does not yet contain a `.battalion` workspace, the bare invocation initializes one from the supplied requirement and then writes assessment artifacts.

Mission intake starts deterministic and no-AI by default. Normal compound requirements such as:

```bash
battalion "Create README.md and CONTRIBUTING.md"
```

are structured locally and preserve each requested artifact as distinct mission intent. For larger or ambiguous requirements where deterministic intake cannot structure the mission confidently, rerun with explicit opt-in:

```bash
battalion --ai-assisted-intake "Describe the mission"
```

The AI-assisted path is limited to mission intake synthesis. It may structure raw human requirements into traceable intent, but deterministic cataloging, playbook matching, and Plan generation still own the authoritative Plan.

Assessment may generate or refresh the mission contract from the authoritative mission requirement. It produces internal artifacts for later Battalion phases:

- `.battalion/assessment.json`
- `.battalion/assessment.md`
- `.battalion/mission-plan.md`

The CLI output is intentionally limited to mission assessment:

- assessment outcome: `UNDERSTOOD`, `PROCEED_WITH_ASSUMPTIONS`, or `CLARIFICATION_REQUIRED`;
- mission type selected from deterministic playbooks;
- mission intent;
- assumptions;
- blocking ambiguity;
- minimal playbook questions;
- recommendation to proceed to planning.

Assessment does not report implementation readiness, engineering obligations, mission assurance, deployment posture, runtime selection, framework selection, or approval to implement. Those belong to planning and assurance.

Assessment does not generate code, execute work, dispatch executors, approve the mission, or recommend implementation.

Battalion asks clarification questions only when the answer materially changes implementation, verification, or mission outcome. Small slices such as documentation updates, data-only migrations, or focused UI changes should not be treated as full-stack missions.

Assessment is driven by packaged mission playbooks. The MVP playbooks cover:

- `api.endpoint`
- `data.model`
- `ui.component`
- `infrastructure.deployment`
- `testing.automated`
- `documentation.readme`
- `documentation.adr`
- `documentation.open_knowledge`

If multiple playbooks match equally, Assessment asks one concise mission-type clarification before planning.

When questions are required and the terminal is interactive, Battalion asks them immediately with simple ordinal numbering:

```text
Assessment needs 3 human answer(s) before it can produce the authoritative Plan.

Question 1 of 3
Which endpoint path should be implemented?
> /health
```

Battalion may keep internal question IDs for traceability, but the human-facing first-run flow does not require Q-ID input. Assessment asks at most five questions in one run. If no questions are needed, it generates the Plan without prompting.

### `battalion plan`

Creates the execution-ready engineering specification.

```bash
battalion plan
```

The normal first-run path is `battalion "Describe the mission"`, which generates the Plan automatically. Use `battalion plan` only to regenerate the Plan from an existing assessed mission or to record manual requirements in legacy/internal workflows.

Planning currently consumes assessment readiness values of `READY` or `READY_WITH_RISK` as deterministic assessment signals before rendering a Plan. The generated Plan does not include readiness classifications or proceed/no-proceed language. It writes:

```text
.battalion/mission-plan.md
```

Architecture reference filenames may be recorded explicitly:

```bash
battalion plan \
  --architecture api-security.md \
  --architecture eventing.md
```

Planning records reference filenames but does not inspect, parse, summarize, or infer intent from architecture documents.

Plan Template v1 is rendered into `.battalion/mission-plan.md`. The plan is the authoritative execution artifact for the mission and includes mission, objective, doctrine and constraints, assumptions, risks, factual planning status, explicit human decisions, traceable requirements with acceptance criteria, concrete deliverables, definitive out-of-scope items, ordered execution strategy, deterministic validation plan, evidence requirements, and definition of complete.

Battalion recommendations are advisory signals only. They do not authorize execution, approve implementation, merge code, deploy systems, or replace human engineering decisions.

Manual requirement entry remains available:

```bash
battalion plan --requirement "Validate JWT issuer" \
  --acceptance "Unknown issuers are rejected" \
  --review architect \
  --review secops \
  --review tester
```

### `battalion dispatch`

Dispatch has two current modes.

Executor handoff sends the engineering specification to a supported executor:

```bash
battalion dispatch --executor codex
battalion dispatch --executor claude-code
battalion dispatch --executor copilot
```

Supported executors:

- Codex
- Claude Code
- GitHub Copilot CLI

Dispatch validates `.battalion/mission-plan.md`, validates the executor, validates recorded architecture reference filenames, creates an executor-specific dispatch package, invokes the executor, waits for completion, and records metadata.

Dispatch packages are written under:

```text
.battalion/dispatches/DSP-001/
```

Dispatch streams executor output when supported. If the executor is quiet, Battalion emits a heartbeat while it waits.

Auto mode permits routine local implementation work by the selected executor:

```bash
battalion dispatch --executor codex --mode auto
```

Auto mode does not authorize commits, pushes, pull requests, merges, deployments, or remote repository modification.

Runtime assignment dispatch remains available without `--executor`:

```bash
battalion dispatch
```

This creates the next sequential assignment from the mission contract. Runtime assignments are local state-management artifacts for Dispatcher validation and future execution integrations.

### `battalion execute`

Simulates unit execution against the active runtime assignment.

```bash
battalion execute --outcome COMPLETE --evidence evidence/asg-001.txt
```

Valid outcomes:

- `COMPLETE`
- `BLOCKED`
- `FAILED`
- `NEEDS_CLARIFICATION`
- `NEEDS_SUPPORT`
- `ABORTED`

`COMPLETE` requires evidence. If evidence is missing, Battalion blocks the assignment instead of accepting completion by assertion.

### `battalion status`

Displays the runtime dashboard.

```bash
battalion status
```

Status includes mission phase, assignments, blocked work, completed work, pending work, clarifications, and Dispatcher recommendation.

### `battalion assure`

Runs Mission Assurance.

```bash
battalion assure
```

Static Assurance is the default:

```bash
battalion assure
```

Static Assurance validates recorded artifacts, evidence files, source-visible contract signals, reviews, schemas, traceability, and audit records.

Runtime Assurance is opt-in:

```bash
battalion assure --run
```

Runtime Assurance validates deterministic local engineering behavior when safe local checks are available. For example, it may inspect localhost HTTP responses and compare observed status codes, JSON bodies, response fields, and timestamps against acceptance criteria.

Runtime Assurance does not deploy, commit, push, create pull requests, call external APIs, or manage executor/runtime setup.

When runtime validation executes, Battalion prints the runtime target it validated:

```text
Runtime Target:
- Base URL: http://127.0.0.1:3000
  Endpoint: /v1/health
  Full URL: http://127.0.0.1:3000/v1/health
```

Default CLI output is concise and shows expected values, observed values, summarized evidence, recommendations, and diagnostics such as stale runtime/build hints. Full evidence is still preserved in `.battalion/assurance.json` and `.battalion/assurance.md`.

To print full runtime evidence in the terminal:

```bash
battalion assure --run --verbose
```

Assurance answers:

> Did we build what we agreed to build?

Assurance validates implementation outputs against the engineering contract: mission prompt, mission contract, assessment, mission plan, acceptance criteria, evidence, and produced artifacts. It is deterministic and evidence-based. It does not use AI, infer unstated intent, judge implementation style, or replace human code review.

Assurance writes:

- `.battalion/assurance.json`
- `.battalion/assurance.md`

Each engineering check returns:

- `VERIFIED`
- `FAILED`
- `UNABLE_TO_VERIFY`

`UNABLE_TO_VERIFY` means Battalion could not prove the criterion deterministically from available artifacts or evidence.

Runtime evidence, when available, is preferred over static evidence because observable engineering behavior is stronger than source inspection.

Assurance separates engineering-contract findings from governance findings. Engineering findings answer whether the implementation satisfies the contract. Governance findings cover reviews, audit integrity, schema validity, and contract lifecycle state.

The overall result still uses:

- status: `GREEN`, `AMBER`, or `RED`
- recommendation: `GO` or `NO-GO`
- confidence
- traceable findings

These statuses are assurance signals and recommendations only. They do not deploy, merge, approve, block, or otherwise own the human engineering decision. `GO` is impossible unless status is `GREEN`.

### `battalion review`

Runs Plan Review v1 against a completed implementation by comparing supplied evidence files to the authoritative Plan.

```bash
battalion review --evidence evidence/tests.txt
```

Plan Review writes:

```text
.battalion/plan-review.md
.battalion/plan-review.json
```

Plan Review answers only:

- What did the Plan require?
- What evidence exists?
- What matches?
- What does not match?
- What could not be verified?

Plan Review reports factual findings and advisory recommendations for human decision-making. It does not approve, reject, merge, deploy, authorize execution, gate work, implement Evidence Report v1, select executors, or modify the authoritative Plan.

Human decisions remain explicit, but humans do not need to manually edit Plan or review artifacts when a pull request already provides deterministic decision evidence. `battalion review` can record observed decision sources:

```bash
battalion review \
  --evidence evidence/tests.txt \
  --decision-evidence "pr-approval=observed:PR #28 approved" \
  --decision-evidence "pr-merge=executed:PR #28 merged"
```

Supported decision sources are `pr-approval`, `pr-merge`, and `manual-artifact`. PR approval may satisfy human review evidence, PR merge may satisfy authorization or completion evidence, and manual artifact updates remain an optional fallback for workflows without a PR. Passing tests, implementation completion, and Battalion recommendations are never inferred as human approval.

### `battalion evidence-report`

Generates Evidence Report v1 from Plan Review output.

```bash
battalion evidence-report
```

Evidence Report consumes:

```text
.battalion/plan-review.json
```

and writes:

```text
.battalion/evidence-report.md
.battalion/evidence-report.json
```

Use `--review` to supply a specific Plan Review JSON file:

```bash
battalion evidence-report --review .battalion/plan-review.json
```

Evidence Report is the concise decision-support artifact produced after Plan Review. It summarizes the Plan and Plan Review versions evaluated, verified findings, failed findings, unable-to-verify findings, out-of-scope deviations, advisory Battalion recommendation, observed human decision evidence, and the explicit human-decision boundary.

Evidence Report does not independently re-evaluate implementation evidence, rewrite Plan Review findings, approve, reject, merge, deploy, authorize execution, or gate work. The latest non-superseded Evidence Report is authoritative; Evidence Report v1 records lineage metadata but does not implement an artifact resolver or catalog.

### `battalion resolve`

Creates a focused implementation correction package from failed Mission Assurance findings.

```bash
battalion resolve
```

Resolve consumes the latest `.battalion/assurance.json` and writes:

```text
.battalion/resolutions/RES-001/
```

The package contains:

- `instructions.md`
- `metadata.yaml`

Resolve includes only `FAILED` engineering checks. It excludes:

- `VERIFIED` checks
- `UNABLE_TO_VERIFY` checks
- governance findings
- pending reviews
- clarification history
- audit history

Resolve preserves the original mission, assessment, mission plan, and assurance report reference. It does not reassess, replan, regenerate requirements, modify acceptance criteria, or redefine mission scope.

To hand failed findings to an executor:

```bash
battalion resolve --executor codex
battalion resolve --executor claude-code
battalion resolve --executor copilot
```

Resolve uses the same executor abstraction and execution modes as Dispatch:

```bash
battalion resolve --executor codex --mode auto
```

The correction loop is:

```text
Mission Context
↓
Assess
↓
Clarify
↓
Plan
↓
Dispatch
↓
Assure
↓
Resolve
↓
Assure
```

Repeat Resolve and Assurance until the Engineering Result is `GREEN`.

### `battalion report`

Renders the mission report.

```bash
battalion report
```

The report is written to:

```text
.battalion/reports/mission-report.md
```

## Mission contract

The mission contract lives in `.battalion/ledger.yaml`.

Requirements contain:

- `id`
- `statement`
- `status`
- `owner`
- `acceptance`
- `evidence`
- `assumptions`
- `risks`
- `required_reviews`
- `traceability`

Requirement statuses:

- `proposed`
- `planned`
- `in_progress`
- `completed`
- `deferred`
- `rejected`
- `accepted_risk`

Final statuses are `completed`, `deferred`, `rejected`, and `accepted_risk`.

Every requirement must have acceptance criteria and required reviews. Completed requirements must have evidence.

## Mission classification

Mission domain detection is deterministic and catalog-driven. The packaged attribute catalog lives at:

```text
battalion/attributes.yml
```

Seeded attributes include:

- `REST_API`
- `HTTP_ENDPOINT`
- `USER_INTERFACE`
- `DATABASE`
- `SECURITY`
- `TESTING_REQUIRED`
- `NODE`
- `TYPESCRIPT`
- `DOTNET`
- `DOCKER`

Each classification result records evidence, source labels, hit count, threshold, and decision. Assessment uses this information only to understand mission scope and select relevant mission playbooks. It does not expand the mission into unrelated project-wide obligations.

## Assurance rules

Mission Assurance returns:

- `GREEN / GO` when requirements are final, acceptance exists, evidence exists where required, reviews are complete, traceability is valid, and the audit trail is valid.
- `AMBER / NO-GO` when mission structure is valid but work remains open, clarifications remain open, or reviews remain pending.
- `RED / NO-GO` when required files are missing, schema is invalid, audit data is invalid, evidence is missing for completed work, or contract data is corrupted.

These are assurance signals and recommendations. They never replace human decision authority.

Failures are specific and traceable. Battalion does not emit generic assurance failures.

## Dispatcher doctrine

The Dispatcher is the sole coordinator of mission state and executor assignments. It does not own human engineering decisions.

Units do not:

- mark missions complete;
- queue additional work;
- approve themselves;
- skip requirements.

Units report facts. The Dispatcher coordinates the next runtime action within the mission state machine.

Sequential execution is enforced. Only one assignment may be active unless a future dispatcher explicitly authorizes parallel execution.

## Engineering compatibility doctrine

Battalion reports compatibility obligations when they are relevant, but it does not decide framework, runtime, SDK, library, package, platform, operating system, cloud service, or standards compatibility for the engineering team.

Human engineers must validate compatibility during implementation, testing, and assurance.

Battalion does not maintain compatibility matrices or act as a dependency resolver.

## Artifact serialization doctrine

Battalion artifacts must be truthful to their declared serialization format:

- `.yaml` means proper YAML.
- `.json` means proper JSON.
- `.jsonl` means JSON Lines.

Battalion does not intentionally serialize JSON into a `.yaml` artifact because a YAML parser would accept it.

## Troubleshooting

### `ModuleNotFoundError: No module named 'yaml'`

Install Battalion into the Python environment that runs the tests:

```bash
python -m pip install -e .
python -m pytest
```

Avoid globally installed `pytest` executables that use a different Python environment than the one where Battalion was installed.

### Command cannot find a mission

Run `battalion "Describe the mission"` in the current directory or navigate to a directory containing `.battalion`.

### Planning says the mission is not ready

Run `battalion "Describe the mission"` with the clarified requirement, or answer the questions Battalion asks during mission intake. Planning currently requires readiness `READY` or `READY_WITH_RISK` as assessment signals. Humans still decide whether to proceed.

## Changelog

Release history lives in [CHANGELOG.md](CHANGELOG.md).
