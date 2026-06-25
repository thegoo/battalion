# Battalion v0.2.0 — Dispatcher Runtime Skeleton

Battalion is a deterministic, local mission-governance and runtime layer for software delivery. Mission Analyst turns an authoritative prompt into a traceable mission contract, humans resolve clarification questions, Mission Assurance independently validates the contract, and the Dispatcher now owns sequential runtime assignment state.

This slice does **not** execute autonomous agents, orchestrate models, call LLMs, provide a web UI, automate GitHub or CI/CD, run background workers, or use cloud/vector storage. `battalion execute` is a local simulation seam for future runners.

## Development installation

Battalion requires Python 3.9 or newer and has no runtime dependencies.

```bash
cd /path/to/battalion
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
which battalion
battalion --help
```

`which battalion` must resolve to the active environment's executable, such as `/path/to/battalion/.venv/bin/battalion`. The project includes a compatibility entry point for older pip versions as well as the standard `pyproject.toml` console script.

For development:

```bash
python3 -m unittest discover -s tests -v
```

## Running a mission anywhere

After installation, leave the repository and create a mission in any directory:

```bash
mkdir -p ~/tmp/hello-world
cd ~/tmp/hello-world

battalion init
# Prompt: Describe the mission:
# Enter: Build a hello world REST API.

battalion plan
battalion clarify
battalion assure
battalion dispatch
battalion execute
battalion status
battalion assure
battalion report
```

Every command locates `.battalion` relative to the current working directory. The repository root, manual imports, custom aliases, and `PYTHONPATH` are not required.

`init` captures the mission prompt and creates `.battalion/mission.yaml`, `agents.yaml`, `ledger.yaml`, `events.jsonl`, and `reports/`. The prompt is stored as `mission_prompt` in both the mission record and initial ledger and is the authoritative source of mission intent. For non-interactive use:

```bash
battalion init --prompt "Build a hello world REST API."
```

The `.yaml` files use JSON syntax, which is valid YAML 1.2 and keeps the CLI dependency-free.

## Mission Analyst planning

Running `battalion plan` without arguments activates the deterministic Mission Analyst. It extracts explicit prompt constraints before creating work. For example:

```bash
battalion init --prompt "Build a TypeScript Node REST API running in Docker with a health endpoint. Allow GET requests only. Follow OWASP guidance. Create happy-path, negative-path, and malicious-request tests."
battalion plan
```

This contract includes distinct requirements for the TypeScript/Node application, health endpoint, Docker packaging, GET-only enforcement, secure error handling, explicitly requested test scenarios, and documentation.

Every generated requirement contains non-empty acceptance criteria, an implementation owner, one or more pending standing-team reviews, and prompt traceability explaining why it exists. Review records include a reason explaining the recommendation. The ledger also contains categorized constraints, low-risk assumptions, risks, and clarification questions with stable IDs.

The resulting `.battalion/ledger.yaml` is the initial mission contract and source of truth. `battalion plan` prints the generated contract for human review, and `battalion report` renders it with its prompt, criteria, assumptions, risks, and reviews.

Generation is local and rule-based. The Mission Analyst does not call an LLM, write code, execute reviews, modify implementation, approve risk, or close the mission.

### Constraint categories

The generated contract stores constraints under `functional`, `technical`, `security`, `testing`, and `operational`. Each constraint records its stable ID, normalized statement, and an exact excerpt from the authoritative prompt.

Recognized Slice 1B.2 constraints include health/API behavior, TypeScript, Node.js, Docker, GET-only access, OWASP guidance, information-disclosure controls, malformed-request handling, happy-path tests, negative-path tests, malicious-request tests, container execution, local execution, and startup instructions.

### Prompt traceability

Every generated requirement, assumption, risk, and clarification stores:

```json
{
  "source": "mission_prompt",
  "prompt_excerpt": "Allow GET requests only.",
  "rationale": "The prompt explicitly restricts allowed HTTP methods to GET.",
  "constraint_ids": ["SC-001"]
}
```

Mission Assurance rejects generated contracts whose trace excerpt does not occur in the immutable mission prompt or whose constraint IDs do not exist. Reports expose both the extracted constraints and the complete traceability map.

### Clarifications versus assumptions

Mission Analyst creates clarification artifacts rather than silently selecting material details. A health API without an endpoint path, framework, timestamp format, or specific OWASP baseline produces open `Q-xxx` questions. Assumptions are limited to low-risk execution prerequisites such as availability of tools explicitly named by the prompt.

Clarifications are first-class mission artifacts with `open`, `resolved`, `superseded`, and `rejected` states. Each artifact stores its question, answer, creation time, resolution time, resolver, prompt traceability, and append-only decision history.

Open clarifications keep Mission Assurance at AMBER / NO-GO; terminal clarification states do not create assurance findings. Malformed lifecycle, history, or traceability data produces RED / NO-GO.

## Clarification resolution

Run the interactive workflow after planning:

```bash
battalion clarify
```

Battalion displays each open question, asks who is resolving it, collects answers, persists the decisions, appends audit events, and runs deterministic Mission Analyst reconciliation.

For non-interactive use, repeat `--answer`:

```bash
battalion clarify --resolver "Jesse Williams" \
  --answer "Q-001=/health" \
  --answer "Q-002=Fastify" \
  --answer "Q-003=ISO-8601 UTC" \
  --answer "Q-004=OWASP API Security Top 10 2023"
```

Other terminal decisions use the same `Q-ID=value` form:

```bash
battalion clarify --resolver "Jesse Williams" --reject "Q-002=Framework decision deferred"
battalion clarify --resolver "Jesse Williams" --supersede "Q-001=/status"
```

Resolution refines requirements in place. For the example above, the contract selects Fastify, changes the health endpoint to `/health`, requires the clarified timestamp format, narrows OWASP acceptance and SecOps scope, and updates related assumptions and risks. Requirement IDs remain stable and no duplicate requirements are created.

Every lifecycle transition appends both contract history and an audit event: `clarification_created`, `clarification_resolved`, `clarification_superseded`, or `clarification_rejected`. Reconciliation emits `mission_contract_reconciled`. This keeps human decisions reconstructable while preserving a schema future agent implementations can consume.

Manual requirement entry remains available when needed:

```bash
battalion plan --requirement "Validate JWT issuer" \
  --acceptance "Unknown issuers are rejected by unit tests" \
  --review architect \
  --review secops \
  --review tester
```

Each generated review begins in `pending`. Run `battalion assure` after `plan` and `clarify` to validate the mission contract before runtime dispatch. At that point Assurance may still return AMBER / NO-GO because work, evidence, or reviews remain incomplete; that is expected. RED / NO-GO means the contract or audit trail is malformed and should be fixed before dispatch.

`dispatch` creates first-class runtime assignments; it does not execute or complete reviews. Run `battalion assure` again after execution evidence and reviews are recorded for the final GREEN / GO decision.

## Dispatcher runtime

The Dispatcher is the only authority allowed to advance runtime execution. Units do not mark missions complete, queue additional work, approve themselves, or skip requirements. Units only report result packets; the Dispatcher consumes those packets and decides the next action.

Runtime state is stored in `.battalion/assignments.yaml`. Assignment records include:

```json
{
  "id": "ASG-001",
  "requirement_id": "R-001",
  "assigned_unit": "developer",
  "status": "ASSIGNED",
  "scoped_context": {},
  "required_outputs": ["code changes", "implementation notes", "evidence references"],
  "dependencies": [],
  "evidence": [],
  "result_packet": null,
  "abort_packet": null,
  "audit_history": []
}
```

Valid assignment states are `CREATED`, `ASSIGNED`, `EXECUTING`, `WAITING`, `COMPLETE`, `BLOCKED`, `FAILED`, and `ABORTED`. Only Dispatcher code changes assignment state, and every state change appends assignment history plus `events.jsonl` audit entries.

### Dispatch

```bash
battalion dispatch
```

`dispatch` reads the mission contract, finds the next non-final requirement, selects the required unit from the requirement owner, creates an assignment, scopes context, persists it, and emits audit events. Sequential execution is enforced: only one assignment may be active at a time. If failed, blocked, or aborted work exists, the Dispatcher halts instead of creating more work.

Scoped context is deliberately narrow. Developer assignments receive the assigned requirement, acceptance criteria, relevant constraints, resolved clarifications, and required evidence references. Mission Assurance and Dispatcher remain the only roles intended to receive full mission context.

### Execute

```bash
battalion execute --outcome COMPLETE --evidence evidence/asg-001.txt
```

`execute` simulates unit execution. It does not call an LLM or external runner. It creates a result packet with one of: `COMPLETE`, `BLOCKED`, `FAILED`, `NEEDS_CLARIFICATION`, `NEEDS_SUPPORT`, or `ABORTED`. The Dispatcher consumes the packet and determines the next action.

Failure outcomes persist an abort packet:

```bash
battalion execute \
  --outcome FAILED \
  --failure-type VALIDATION_FAILED \
  --reason "Unit tests failed" \
  --impact "Cannot validate requirement" \
  --recommendation "Return work to Developer" \
  --decision-action return_work_to_previous_unit
```

Failure types are `MISSING_CONTEXT`, `DEPENDENCY_MISSING`, `VALIDATION_FAILED`, `SECURITY_BLOCKER`, `TOOL_FAILURE`, `PERMISSION_DENIED`, `UNRECOVERABLE_ERROR`, and `OTHER`.

Dispatcher decisions include dispatching the next assignment, retrying an assignment, returning work to a previous unit, requesting support, generating a clarification, escalating to a human, accepting risk, or aborting the mission. Every decision creates an audit event.

### Status

```bash
battalion status
```

`status` is the runtime dashboard. It displays the mission, current phase, assignments, unit assignments, blocked work, completed work, pending work, clarifications, and the Dispatcher recommendation.

For v0.2.0, clarification decisions are recorded through `battalion clarify`. Run `battalion assure` immediately after clarification resolution to validate the contract before dispatching runtime work:

```bash
battalion assure
```

Runtime outcomes are recorded through `battalion dispatch` and `battalion execute`. Review decisions remain governance records in `ledger.yaml`: complete reviews and ensure project-relative evidence paths exist. Then run final assurance and reporting:

```bash
battalion assure
battalion report
```

`report` writes `.battalion/reports/mission-report.md` and leaves human approval pending. Only a human can close the mission.

If `plan`, `clarify`, `dispatch`, `execute`, `status`, `assure`, or `report` is run outside a mission directory, Battalion exits without a traceback and explains how to run `battalion init` or navigate to a directory containing `.battalion`.

## Requirement contract

Every requirement must contain these fields:

```json
{
  "id": "R-001",
  "statement": "Validate JWT issuer",
  "status": "completed",
  "owner": "developer",
  "acceptance": [
    "Unit tests reject unknown issuers",
    "Issuer validation is documented"
  ],
  "evidence": [
    "tests/test_auth.py",
    "docs/auth.md"
  ],
  "assumptions": ["A single identity provider is configured"],
  "risks": ["Key rotation is not implemented"],
  "required_reviews": [
    {"reviewer": "architect", "status": "completed"},
    {"reviewer": "secops", "status": "completed"},
    {"reviewer": "tester", "status": "completed"}
  ]
}
```

Required fields are `id`, `statement`, `status`, `acceptance`, `evidence`, and `required_reviews`. Supported requirement states are `proposed`, `planned`, `in_progress`, `completed`, `deferred`, `rejected`, and `accepted_risk`. Final states are `completed`, `deferred`, `rejected`, and `accepted_risk`.

### Acceptance criteria

`acceptance` must be a non-empty list of non-blank criteria for every requirement. Missing, empty, or malformed acceptance criteria produce RED / NO-GO.

### Evidence

Every completed requirement must have at least one non-blank evidence path. Evidence paths must resolve to files inside the governed project; missing files, absolute paths outside the project, and traversal outside the project produce RED / NO-GO. Non-completed requirements may have an empty evidence list.

### Required reviews

`required_reviews` must be a non-empty list. Each record names a reviewer from the generated standing team and has status `pending` or `completed`.

- Missing, empty, malformed, duplicate, or unknown reviews produce RED / NO-GO.
- A valid pending review keeps the mission AMBER / NO-GO.
- Every required review must be completed before GREEN is possible.

Review records are governance artifacts in v0.2.0. Battalion does not execute the reviewers.

## Audit validation

Mission Assurance verifies that `events.jsonl`:

- exists and is readable;
- is non-empty JSON Lines data;
- contains object events with valid `timestamp`, `type`, `actor`, and `details` fields;
- contains a `mission_initialized` event whose mission ID matches `mission.yaml`.

Every malformed line is reported. An absent or mismatched initialization event produces RED / NO-GO.

Assurance output and mission reports summarize open, resolved, superseded, and rejected clarification counts separately from findings. After all questions are resolved, clarification findings disappear while incomplete requirements and pending reviews continue to produce AMBER / NO-GO.

## Assurance decisions

- **GREEN / GO:** at least one requirement exists; every requirement is final; every requirement has acceptance criteria; completed requirements have resolvable evidence; accepted risks have risk entries; all required reviews are completed; and the audit trail is valid.
- **AMBER / NO-GO:** mission structure is valid, but no requirements exist, work remains open, a clarification remains open, or a valid required review remains pending.
- **RED / NO-GO:** required files are missing; mission, team, requirement, review, constraint, clarification, traceability, or audit data is malformed; acceptance criteria or required reviews are missing; completed evidence is missing or cannot be resolved; or accepted risk lacks a risk entry.

GO is structurally prohibited unless status is GREEN. Assurance is deterministic: identical workspace inputs produce the same status, recommendation, confidence, and ordered findings.

Findings identify the mission or requirement and the precise failed contract rule. Validation accumulates failures rather than silently ignoring malformed data or stopping after the first problem.

## Doctrine

Battalion preserves eight principles: mission first; evidence over assertion; requirement traceability; zero trust; adversarial review; separation of duties; human authority; and an audit trail for every material CLI action.

## Standing team

Generated `agents.yaml` defines Mission Analyst, Architect, SecOps, DevOps, UX, Developer, Tester, SRE, and Mission Assurance, including their charters, prohibited actions, and required outputs. Mission Analyst is operational only as the deterministic contract generator described above. The other roles remain governance records, not executable agents.

See `examples/jwt-auth-mission` for a complete local fixture.
