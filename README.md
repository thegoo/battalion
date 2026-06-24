# Battalion v0.1.4 — Constraint Extraction & Prompt Traceability

Battalion is a deterministic, local mission-governance layer for software delivery. The Mission Analyst extracts explicit functional, technical, security, testing, and operational constraints from the immutable mission prompt, then creates a traceable mission contract.

This slice does **not** execute autonomous agents, orchestrate models, call LLMs, provide a web UI, automate GitHub or CI/CD, run background workers, or use cloud/vector storage.

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
battalion dispatch
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

Clarifications have `open` or `resolved` status. Open clarifications keep Mission Assurance at AMBER / NO-GO; malformed clarification or traceability data produces RED / NO-GO.

Manual requirement entry remains available when needed:

```bash
battalion plan --requirement "Validate JWT issuer" \
  --acceptance "Unknown issuers are rejected by unit tests" \
  --review architect \
  --review secops \
  --review tester
```

Each generated review begins in `pending`. `dispatch` records a simulated dispatch and advances proposed requirements to `planned`; it does not execute or complete reviews. Assurance therefore returns AMBER / NO-GO after initial planning and dispatch because execution and reviews remain incomplete—not because planning artifacts are missing.

For v0.1.4, implementation outcomes, clarification resolutions, and review decisions are recorded by editing `ledger.yaml`. Set clarifications and reviews to `resolved` or `completed`, set the requirement status, and add project-relative evidence paths. Then run:

```bash
battalion assure
battalion report
```

`report` writes `.battalion/reports/mission-report.md` and leaves human approval pending. Only a human can close the mission.

If `plan`, `dispatch`, `assure`, or `report` is run outside a mission directory, Battalion exits without a traceback and explains how to run `battalion init` or navigate to a directory containing `.battalion`.

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

Review records are governance artifacts in v0.1.4. Battalion does not execute the reviewers.

## Audit validation

Mission Assurance verifies that `events.jsonl`:

- exists and is readable;
- is non-empty JSON Lines data;
- contains object events with valid `timestamp`, `type`, `actor`, and `details` fields;
- contains a `mission_initialized` event whose mission ID matches `mission.yaml`.

Every malformed line is reported. An absent or mismatched initialization event produces RED / NO-GO.

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
