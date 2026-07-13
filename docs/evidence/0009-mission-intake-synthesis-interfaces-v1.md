# Mission Intake Synthesis Interfaces v1 Evidence

## Base and Setup

- Base branch confirmation: fetched `origin`; `HEAD`, `main`, and `origin/main` matched `a08c82e32b898b1c4272a0e0a9edcb3a8f4d014e`.
- Working branch: `codex/mission-intake-synthesis-v1`.
- Setup friction: `source .venv/bin/activate && python -m pip install -e .` initially failed because `.venv/bin/activate` did not exist in the worktree.
- Created `.venv`, reran editable install, and allowed network for pip dependency resolution after the sandbox blocked PyPI access.

## Failed Dogfood Evidence

Exact pre-fix dogfood command:

```bash
source .venv/bin/activate && battalion "Mission Intake Synthesis Interfaces v1. Battalion should lead with no AI first. Deterministic intake must handle normal compound requirements, especially battalion Create README.md and CONTRIBUTING.md, without collapsing scope. AI-assisted mission synthesis is opt-in via command argument flag for larger or ambiguous requirements. If deterministic intake judges a requirement too large or complex to structure confidently, it must stop clearly and recommend rerunning with the AI-assisted synthesis argument. Build interfaces and contracts to support AI-assisted intake later without requiring a provider. AI synthesis is allowed only during mission intake to turn raw human requirements into explicit structured intent. AI synthesis does not decide approve implement or generate the final Plan freehand. Deterministic cataloging playbook matching and Plan generation still own the authoritative Plan. Structured synthesis output must be traceable to the original human requirement. Original mission text must remain unchanged. Preserve doctrine Battalion owns WHAT executors own HOW humans own decisions evidence over assertion Battalion remains boring. Expected behavior default battalion Create README.md and CONTRIBUTING.md preserves both artifacts. Opt-in AI path uses explicit flag discoverable in help docs. Too-large deterministic input stops with non-destructive error recommending AI-assisted intake and no fabricated Plan. Preserve bare invocation and explicit command behavior. Include tests evidence and retrospective."
```

Observed failure:

- Output was `CLARIFICATION_REQUIRED`.
- Understanding included `Create a README documentation artifact.`
- `CONTRIBUTING.md` was not preserved in understanding.
- A stale CLI compatibility question remained after answering that assessment should remain internal-only.
- No authoritative Plan was generated.

## Focused TDD Evidence

Focused tests were added before implementation:

- `test_compound_docs_mission_preserves_distinct_requested_artifacts`
- `test_compound_docs_questions_are_not_readme_only`
- `test_default_intake_is_deterministic_no_ai`
- `test_ai_assisted_intake_flag_routes_to_stub_without_provider`
- `test_too_complex_deterministic_intake_recommends_ai_assisted_without_plan`
- Updated `test_cli_help_executes_successfully` to require `--ai-assisted-intake`.

Initial focused result:

```text
6 failed, 194 deselected
```

Expected failures showed missing help exposure, missing flag routing, missing structured intake output, compound docs collapsing to README-only acceptance, and too-complex deterministic input producing a misleading Plan instead of stopping.

Final focused result:

```text
6 passed, 194 deselected
```

## Corrected Dogfood Evidence

Compound docs now preserve both artifacts:

```bash
source .venv/bin/activate && battalion "Create README.md and CONTRIBUTING.md"
```

Result:

- Assessment outcome: `PROCEED_WITH_ASSUMPTIONS`
- Understanding includes README.md and CONTRIBUTING.md as distinct documentation artifacts.
- Questions: None.
- Authoritative Plan generated at `.battalion/mission-plan.md`.

Too-complex deterministic intake now stops:

```text
battalion: error: Deterministic intake cannot structure this mission confidently. Rerun with --ai-assisted-intake to opt in to AI-assisted intake synthesis.
```

Opt-in dogfood for this slice now generates the authoritative Plan:

```bash
source .venv/bin/activate && battalion --ai-assisted-intake "Mission Intake Synthesis Interfaces v1. ..."
```

Result:

- Assessment outcome: `PROCEED_WITH_ASSUMPTIONS`
- Mission type: `CLI / Workflow`
- Questions: None.
- Authoritative Plan: `.battalion/mission-plan.md`.

## Requirement Evidence

- R-001 PASS: `battalion/intake.py` defines deterministic and AI-assisted stub synthesizer boundaries and traceable structured output.
- R-002 PASS: compound Markdown artifact extraction records README.md and CONTRIBUTING.md distinctly, and mission-contract generation creates separate documentation requirements.
- R-003 PASS: `--ai-assisted-intake` is accepted for bare mission intake, visible in help, documented, and routed to a stub without provider calls.
- R-004 PASS: deterministic intake refuses over-complex input before Plan generation and recommends the opt-in flag.
- R-005 PASS: existing no-arg, unsupported command, unquoted junk, reserved command, and explicit subcommand behavior remains covered by the existing suite.

## Full Test Result

Command:

```bash
source .venv/bin/activate && pytest
```

Result:

```text
200 passed in 29.07s
```
