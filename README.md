# Battalion

Battalion is a deterministic, local mission-governance layer for software delivery.

It turns an authoritative mission prompt into a traceable mission contract, assesses whether enough engineering information exists to proceed, produces an implementation-ready engineering specification, dispatches that specification to a selected executor, and independently verifies completed work through Mission Assurance.

Battalion is designed around a simple doctrine:

- Mission first.
- Evidence over assertion.
- Requirement traceability.
- Trust nothing. Verify everything.

Battalion does not call LLM APIs, choose models, configure agents, deploy systems, merge code, or approve work by assertion. It coordinates the mission contract and records evidence.

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

## Core workflow

The primary workflow is:

```bash
battalion init
battalion assess
battalion clarify
battalion assess
battalion plan
battalion dispatch --executor codex
battalion assure
battalion report
```

Use `battalion clarify` only when assessment reports open clarifications. Use `battalion assure` after implementation evidence and reviews exist.

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

Multiline YAML values, such as mission prompts, are written as readable block scalars.

## Commands

### `battalion init`

Initializes a mission workspace.

```bash
battalion init \
  --title "Health API" \
  --objective "Build a REST API health endpoint." \
  --prompt "Build a production-ready REST API that exposes a single application health endpoint."
```

`init` creates the mission record, standing team record, attribute catalog, ledger, audit file, and reports directory. The mission prompt is authoritative and remains immutable mission input.

### `battalion assess`

Evaluates whether the mission is ready for the next engineering activity.

```bash
battalion assess
```

Assessment may generate or refresh the mission contract from the mission prompt. It produces:

- `.battalion/assessment.json`
- `.battalion/assessment.md`

Assessment reports:

- mission classification;
- generated requirements;
- acceptance criteria;
- constraints;
- assumptions;
- risks;
- open clarifications;
- engineering readiness;
- recommended next action.

Readiness values are:

- `NOT_READY`
- `PARTIALLY_READY`
- `READY_WITH_RISK`
- `READY`

Assessment does not generate code, execute work, dispatch executors, or approve the mission.

Use interactive assessment only when you explicitly want assessment to collect clarification answers:

```bash
battalion assess --interactive
```

### `battalion clarify`

Collects answers for open clarification questions.

```bash
battalion clarify
```

The interactive workflow lets you answer all, answer one, skip, or exit. Previously resolved clarifications are not shown.

Non-interactive resolution is also supported:

```bash
battalion clarify --resolver "Jesse Williams" \
  --answer "Q-001=/health" \
  --answer "Q-002=Fastify" \
  --answer "Q-003=ISO-8601 UTC"
```

Other terminal decisions:

```bash
battalion clarify --resolver "Jesse Williams" --reject "Q-002=Framework decision deferred"
battalion clarify --resolver "Jesse Williams" --supersede "Q-001=/status"
```

Clarification decisions are persisted in the mission contract and audit trail. Contract reconciliation updates affected requirements without changing stable requirement IDs.

### `battalion plan`

Creates the execution-ready engineering specification.

```bash
battalion plan
```

Planning requires assessment readiness of `READY` or `READY_WITH_RISK`. It writes:

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

Assurance validates the mission contract, evidence, required reviews, traceability, and audit trail. It produces:

- status: `GREEN`, `AMBER`, or `RED`
- recommendation: `GO` or `NO-GO`
- confidence
- traceable findings

`GO` is impossible unless status is `GREEN`.

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

Mission Classification is deterministic and catalog-driven. The attribute catalog lives at:

```text
.battalion/attributes.yml
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

Each classification result records evidence, source labels, hit count, threshold, and decision. Assessment consumes detected attributes when applying Battalion-owned engineering obligations.

## Assurance rules

Mission Assurance returns:

- `GREEN / GO` when requirements are final, acceptance exists, evidence exists where required, reviews are complete, traceability is valid, and the audit trail is valid.
- `AMBER / NO-GO` when mission structure is valid but work remains open, clarifications remain open, or reviews remain pending.
- `RED / NO-GO` when required files are missing, schema is invalid, audit data is invalid, evidence is missing for completed work, or contract data is corrupted.

Failures are specific and traceable. Battalion does not emit generic assurance failures.

## Dispatcher doctrine

The Dispatcher is the only authority allowed to advance runtime execution.

Units do not:

- mark missions complete;
- queue additional work;
- approve themselves;
- skip requirements.

Units report facts. The Dispatcher decides the next action.

Sequential execution is enforced. Only one assignment may be active unless a future dispatcher explicitly authorizes parallel execution.

## Engineering compatibility doctrine

Battalion assesses engineering readiness, not implementation correctness.

Framework, runtime, SDK, library, package, platform, operating system, cloud service, and standards compatibility remain the responsibility of the engineering team. Human engineers must validate compatibility during implementation, testing, and assurance.

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

Run `battalion init` in the current directory or navigate to a directory containing `.battalion`.

### Planning says the mission is not ready

Run:

```bash
battalion assess
battalion clarify
battalion assess
```

Planning requires readiness `READY` or `READY_WITH_RISK`.

## Changelog

Release history lives in [CHANGELOG.md](CHANGELOG.md).
