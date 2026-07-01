# Battalion v0.3.5 — Classification Evidence Refinement

Battalion is a deterministic, local mission-governance and runtime layer for software delivery. Mission Analyst turns an authoritative prompt into a traceable mission contract, Mission Assessment evaluates whether engineering work is ready to begin, humans resolve clarification questions, Mission Assurance independently validates completed work, and the Dispatcher owns sequential runtime assignment state.

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
# Prompt: Mission title:
# Enter: Hello World REST API
# Prompt: Mission objective:
# Enter: Build a simple REST API with a single health check endpoint.
# Prompt: Mission prompt:
# Enter: Build a hello world REST API.

battalion assess
battalion plan
battalion dispatch
battalion execute
battalion status
battalion assure
battalion report
```

Every command locates `.battalion` relative to the current working directory. The repository root, manual imports, custom aliases, and `PYTHONPATH` are not required.

`init` captures the mission title, objective, and prompt, then creates `.battalion/mission.yaml`, `agents.yaml`, `attributes.yaml`, `ledger.yaml`, `events.jsonl`, and `reports/`. It does not require requirements yet. The prompt is stored as `mission_prompt` in both the mission record and initial ledger and is the authoritative source of mission intent. For non-interactive use:

```bash
battalion init \
  --title "Hello World REST API" \
  --objective "Build a simple REST API with a single health check endpoint." \
  --prompt "Build a hello world REST API."
```

The `.yaml` files use JSON syntax, which is valid YAML 1.2 and keeps the CLI dependency-free.

## Mission Assessment as the front door

The primary MVP workflow is:

```bash
battalion init
battalion assess
battalion plan
```

`assess` is the first command that understands the mission. If the ledger does not yet contain requirements, `battalion assess` invokes the deterministic Mission Analyst to generate or refresh the mission contract directly from the immutable mission prompt. For example:

```bash
battalion init --prompt "Build a TypeScript Node REST API running in Docker with a health endpoint. Allow GET requests only. Follow OWASP guidance. Create happy-path, negative-path, and malicious-request tests."
battalion assess
```

This contract includes distinct requirements for the TypeScript/Node application, health endpoint, Docker packaging, GET-only enforcement, secure error handling, explicitly requested test scenarios, and documentation.

Every generated requirement contains non-empty acceptance criteria, an implementation owner, one or more pending standing-team reviews, and prompt traceability explaining why it exists. Review records include a reason explaining the recommendation. The ledger also contains categorized constraints, low-risk assumptions, risks, and clarification questions with stable IDs.

The resulting `.battalion/ledger.yaml` is the mission contract and source of truth. `battalion assess` writes the contract, evaluates readiness, and renders `.battalion/assessment.json` plus `.battalion/assessment.md`. `battalion report` renders the contract with its prompt, criteria, assumptions, risks, and reviews.

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

Open clarifications are part of assessment readiness. Resolve them with the dedicated clarification workflow:

```bash
battalion clarify
```

Battalion displays only unresolved questions and lets you answer all, answer one, skip, or exit. It asks who is resolving answered clarifications, persists the decisions, appends audit events, and runs deterministic Mission Analyst reconciliation. Previously answered clarifications remain resolved and are not shown again.

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

Default `battalion assess` never prompts for clarification answers. If open clarifications exist, Battalion does not pretend readiness is final. It prints primary findings, outstanding clarification IDs and questions, and the command to run next:

```text
Primary Findings
- Open clarifications must be resolved before planning.

Outstanding Clarifications
- Q-001: What endpoint path should be used?

Recommendation: Resolve Clarifications

Run:
  battalion clarify
```

Skipped clarification answers remain `open`; readiness remains `NOT_READY` and the recommendation remains `Resolve Clarifications`.

If you want the convenience workflow, opt in explicitly:

```bash
battalion assess --interactive
```

Interactive assessment runs the normal assessment first. If unresolved clarifications exist, it prompts for answers, persists them, reconciles the mission contract, re-runs assessment automatically, and displays updated readiness. This is a convenience path; `battalion clarify` remains the dedicated clarification workflow.

Manual requirement entry remains available when needed:

```bash
battalion plan --requirement "Validate JWT issuer" \
  --acceptance "Unknown issuers are rejected by unit tests" \
  --review architect \
  --review secops \
  --review tester
```

Each generated review begins in `pending`. Run `battalion assess` after `init` to evaluate whether enough engineering information exists to responsibly begin implementation. Mission Assessment may generate the mission contract and write assessment artifacts, but default assessment does not collect clarification answers, generate code, create runtime assignments, dispatch work, or approve completed work.

Run `battalion plan` after assessment to produce the execution-ready mission plan. Run `battalion assure` only when you need the independent evidence/audit gate. At planning time Assurance may still return AMBER / NO-GO because work, evidence, or reviews remain incomplete; that is expected. RED / NO-GO means the contract or audit trail is malformed and should be fixed before dispatch.

`dispatch` creates first-class runtime assignments; it does not execute or complete reviews. Run `battalion assure` again after execution evidence and reviews are recorded for the final GREEN / GO decision.

## Mission Assessment

```bash
battalion assess
```

Mission Assessment answers:

> Do we have sufficient information to responsibly begin the next engineering activity?

It is distinct from Mission Assurance, which answers whether completed engineering work has enough evidence to be accepted.

Assessment evaluates mission understanding, mission classification, outstanding clarifications, assumptions, risks, engineering obligations, discipline findings, readiness, and the recommended next action. If requirements are missing, it generates the mission contract from the prompt first. It never generates code, creates runtime assignments, dispatches work, or approves completed work.

`battalion assess` writes two deterministic artifacts:

- `.battalion/assessment.json` — canonical machine-readable assessment
- `.battalion/assessment.md` — human-readable report rendered from the JSON

Repeated assessment against unchanged mission inputs produces identical CLI output, JSON, and Markdown.

Readiness levels are:

- `NOT_READY`
- `PARTIALLY_READY`
- `READY_WITH_RISK`
- `READY`

Recommendations are selected deterministically from:

- `Resolve Clarifications`
- `Refine Requirements`
- `Perform Architecture Review`
- `Perform Security Review`
- `Complete Mission Planning`
- `Proceed to Implementation`

Every readiness result includes `readiness_reason`, and every recommendation includes `recommendation_reason`. The CLI prioritizes primary findings, outstanding clarifications, and the next recommended command. The Markdown report expands obligation details, readiness reasons, and recommendation rationale, and `assessment.json` stores the canonical data for Mission Planning and Dispatcher slices.

## Mission Classification

Mission Classification is a standalone deterministic step consumed by Mission Assessment:

```text
Mission Contract
↓
Mission Classifier
↓
Detected Attributes
↓
Assessment Engine
```

The classifier determines engineering attributes only. It does not contain readiness rules, recommendation logic, engineering obligations, or assurance logic.

The attribute catalog lives at `.battalion/attributes.yaml`. The file is JSON-formatted YAML and can be extended by a project or enterprise without changing Battalion code. Each attribute contains:

- `identifier`
- `description`
- `indicators`
- `minimum_threshold`

Seeded attributes include `REST_API`, `HTTP_ENDPOINT`, `USER_INTERFACE`, `DATABASE`, `SECURITY`, `TESTING_REQUIRED`, `NODE`, `TYPESCRIPT`, `DOTNET`, and `DOCKER`, plus compatibility attributes used by existing obligation applicability such as `GET_ONLY`, `SECURE_ERROR_HANDLING`, `MALICIOUS_TESTING`, and `AUTHENTICATION`.

For each catalog attribute, Mission Classification records:

- detected attribute identifier;
- classification evidence with indicator and source;
- hit count;
- threshold;
- classification decision.

Example assessment output:

```text
Mission Classification
- REST_API: classified; evidence [api from mission_prompt, rest from mission_prompt, endpoint from requirement]; hit count 3; threshold 2
- DOCKER: classified; evidence [docker from mission_prompt]; hit count 1; threshold 1
```

`assessment.json` includes the canonical `mission_classification` object, and `assessment.md` includes a Mission Classification section. Assessment consumes the resulting `mission_attributes` list when applying Battalion-owned obligation packs.

Mission Assessment uses built-in Engineering Obligation Packs for Mission Analyst, Architect, Developer, Tester, SecOps, DevOps, SRE, and UX. Each obligation defines when it applies, required disposition, description, severity, category, and finding message. Only applicable obligations appear in the assessment. The implementation keeps obligation data separate from CLI handling so future organization-specific packs can be introduced without turning `battalion assess` into hardcoded prompt logic.

Assessment receives mission attributes from Mission Classification. `assessment.json` also records `attribute_sources` as a compact compatibility map for the detected attributes.

Risks are categorized deterministically as Security, Architecture, Operational, Implementation, or Documentation. If a clarification resolves a previously unknown item, the assessment marks the corresponding risk as resolved in `resolved_risks` instead of continuing to present it as an open contradiction. The canonical JSON also includes `resolved_assumptions` and `finding_categories`.

## Mission planning

```bash
battalion plan
```

`plan` consumes `.battalion/assessment.json` and the assessed mission contract. It turns assessment output into `.battalion/mission-plan.md`, an execution-ready markdown plan containing the mission, readiness, recommendation rationale, requirements, acceptance criteria, required reviews, clarifications, assumptions, risks, constraints, and next execution steps.

Planning depends on assessment. If no assessment exists, Battalion exits cleanly with:

```text
No mission assessment exists. Run battalion assess first.
```

`plan` does not regenerate unrelated or contradictory requirements. Manual requirement entry remains available through `battalion plan --requirement ...` for compatibility and direct contract editing, but the primary documented workflow is `init → assess → plan`.

## Dispatcher runtime

The Dispatcher is the only authority allowed to advance runtime execution. Units do not mark missions complete, queue additional work, approve themselves, or skip requirements. Units only report result packets; the Dispatcher consumes those packets and decides the next action.

Runtime state is stored in `.battalion/assignments.yaml`. Assignment records include:

```json
{
  "id": "ASG-001",
  "requirement_id": "R-001",
  "assigned_unit": "developer",
  "assignment_type": "implementation",
  "ownership": "owned",
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

Valid assignment states are `CREATED`, `ASSIGNED`, `EXECUTING`, `WAITING`, `BLOCKED`, `COMPLETE`, `FAILED`, and `ABORTED`. Only Dispatcher code changes assignment state, and every state change appends assignment history plus `events.jsonl` audit entries.

Assignments remain owned by their assigned unit until the Dispatcher completes, reassigns, or aborts the work. `BLOCKED` and `WAITING` assignments remain active and keep the same assignment ID, scoped context, ownership, evidence, and audit history. A retry does not create a replacement assignment.

### Dispatch

```bash
battalion dispatch
```

`dispatch` reads the mission contract, finds the next non-final requirement, selects the required unit from the requirement owner, creates an assignment, scopes context, persists it, and emits audit events. Sequential execution is enforced: only one assignment may be active at a time. If failed, blocked, or aborted work exists, the Dispatcher halts instead of creating more work.

Scoped context is deliberately narrow. Developer assignments receive the assigned requirement, acceptance criteria, relevant constraints, resolved clarifications, and required evidence references. Mission Assurance and Dispatcher remain the only roles intended to receive full mission context.

Dispatcher assignment order is lifecycle-aware:

- Pending Architect reviews are dispatched before implementation.
- Owner implementation is dispatched only after planning/design reviews are satisfied.
- `battalion dispatch --allow-implementation-before-reviews` explicitly overrides that planning/design gate.
- Tester review assignments are dispatched only after implementation evidence exists.
- Requirements are not marked `completed` until implementation evidence exists and required reviews are complete.

### Execute

```bash
battalion execute --outcome COMPLETE --evidence evidence/asg-001.txt
```

`execute` simulates unit execution. It does not call an LLM or external runner. It creates a result packet with one of: `COMPLETE`, `BLOCKED`, `FAILED`, `NEEDS_CLARIFICATION`, `NEEDS_SUPPORT`, or `ABORTED`. The Dispatcher consumes the packet and determines the next action.

`COMPLETE` requires evidence. If a unit reports `COMPLETE` without evidence, the Dispatcher converts the result to `BLOCKED`, records an abort packet with `MISSING_CONTEXT`, and recommends retrying with evidence. Units cannot mark requirements complete by assertion.

If an assignment is `BLOCKED` or `WAITING`, run `battalion execute` again with evidence to remediate the same assignment:

```bash
battalion execute --outcome COMPLETE --evidence evidence/asg-001.txt
```

The Dispatcher resumes the same assignment, accumulates the evidence, and re-evaluates it. The retry path emits `assignment_waiting`, `assignment_resumed`, and either `assignment_completed` or `assignment_failed`; it does not create `ASG-002` for the same work.

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

For v0.3.5, clarification decisions are normally recorded through `battalion clarify`; `battalion assess --interactive` is available as an explicit convenience workflow. Run `battalion assess` again after clarification resolution to evaluate implementation readiness:

```bash
battalion assess
```

Run `battalion assure` when you need to validate the contract and audit trail before dispatching runtime work:

```bash
battalion assure
```

Runtime outcomes are recorded through `battalion dispatch` and `battalion execute`. Review decisions remain governance records in `ledger.yaml`: complete reviews and ensure project-relative evidence paths exist. Then run final assurance and reporting:

```bash
battalion assure
battalion report
```

`report` writes `.battalion/reports/mission-report.md` and leaves human approval pending. Only a human can close the mission.

If `plan`, `clarify`, `assess`, `dispatch`, `execute`, `status`, `assure`, or `report` is run outside a mission directory, Battalion exits without a traceback and explains how to run `battalion init` or navigate to a directory containing `.battalion`.

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

Review records are governance artifacts in v0.3.5. Battalion does not execute the reviewers.

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
