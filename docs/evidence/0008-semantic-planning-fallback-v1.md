# Semantic Planning Fallback v1 Evidence

## Requirement Evidence

- R-001 PASS: `battalion/playbooks.yml` adds `cli.workflow` for CLI workflow and command-routing work, with command, subcommand, parser, argument, terminal, interactive, prompt, routing, and Battalion indicators. `battalion/attributes.yml` adds a `CLI` mission attribute. The exact bare-command UX dogfood mission now assesses as `CLI / Workflow`.
- R-002 PASS: `battalion/mission_analyst.py` adds a CLI workflow contract with requirements for bare requirement routing, explicit subcommands, interactive assessment, structured answers, automatic initialization, Plan generation, assess compatibility, and tests. The regenerated dogfood Plan does not include generic application entrypoint requirements, HTTP/request-response error handling, deployment-environment risk, or unrelated application boilerplate.
- R-003 PASS: `battalion/assessment.py` now treats low-confidence unknown missions as `CLARIFICATION_REQUIRED`, and `battalion/mission_analyst.py` records `planning_status: insufficiently_understood` without traceable implementation requirements when no supported planning signal exists. The regression test proves no authoritative Plan is generated for `Make it better.`
- R-004 PASS: Understood missions still generate deterministic requirement IDs and traceability. Unsupported missions still generate deterministic assessment artifacts, but they report uncertainty instead of converting vague input into fabricated implementation obligations.
- R-005 PASS: `tests/test_cli.py` adds regression coverage for the exact bare-command UX mission and low-confidence unknown fallback.
- R-006 PASS: `tests/test_cli.py` adds strict TDD coverage proving structured human decisions regenerate the stricter bare-invocation UX Plan; the same original mission plus the same structured human decisions reproduces the exact same Plan on a repeated run; the original mission prompt and structured answers remain unchanged; missing decisions do not invent the strict semantics; conflicting decisions produce `planning_status: conflicting_human_decisions`; malformed decision data produces `planning_status: invalid_human_decisions`; and stale Plans are removed when planning is blocked.

## TDD Evidence

Focused tests were added before implementation:

- `test_cli_ux_human_decisions_regenerate_strict_bare_invocation_plan`
- `test_cli_ux_missing_human_decisions_do_not_invent_strict_semantics`
- `test_cli_ux_conflicting_human_decisions_are_surfaced_before_planning`
- `test_malformed_human_decision_data_fails_clearly_before_planning`

Initial focused result:

```text
3 failed, 1 passed
```

The expected failures showed that Battalion still emitted permissive CLI Plan language, ignored conflicting structured answers, and generated requirements from malformed answer data.

Final focused result:

```text
4 passed
```

The happy-path test also re-runs Battalion after regeneration and asserts that `.battalion/mission-plan.md` is byte-for-byte unchanged, while `mission.yaml` retains the original mission prompt and `ledger.yaml` retains the same structured `human_answers`.

## Regenerated Dogfood Plan

Command:

```bash
.venv/bin/battalion assess $'For the best user experience, a user should not have to know or enter an assessment command.\n\nThe primary interface should simply be:\n\nbattalion "My requirement."\n\nBattalion should automatically initialize if necessary, assess the mission, interactively gather any required human answers (up to the configured maximum), and generate the authoritative Plan in the same flow.\n\nPreserve all existing doctrine and behavior:\n- Battalion owns the WHAT.\n- Humans own answers and decisions.\n- Plans remain authoritative.\n- Evidence over assertion.\n- Battalion remains boring.\n\nThe goal of this slice is to make the default user experience intent-first while preserving all existing assessment, planning, review, and evidence behavior.'
```

Result:

- Assessment outcome: `PROCEED_WITH_ASSUMPTIONS`
- Confidence: High
- Mission type: `CLI / Workflow`
- Mission intent: `Create or update the requested CLI workflow.`
- Questions: None
- Authoritative Plan: `.battalion/mission-plan.md`

The regenerated Plan includes:

- bare requirement routing to assessment;
- preservation of explicit subcommands;
- interactive assessment and structured answers;
- automatic initialization and Plan generation;
- assess compatibility/removal decision;
- help/docs/tests;
- command-name collision and parser regression risks.

The regenerated Plan from structured human decisions now additionally includes:

- `battalion "My requirement."` is the only supported mission-start path;
- no arguments produce a clear error;
- unsupported single-token input such as `battalion frobnicate` produces a clear error;
- unquoted multi-token junk produces a clear error;
- reserved-command collisions are handled clearly and deterministically;
- quoted and multiline natural-language requirements are accepted as valid mission arguments;
- `assess` is removed from public CLI routing and help;
- assessment remains internal workflow logic only.

The regenerated Plan excludes:

- generic application entrypoint requirements;
- HTTP/request-response error handling language;
- deployment-environment risk;
- unrelated application boilerplate.

## Test Evidence

Command:

```bash
python3 -m pytest
```

Result:

```text
186 passed, 1 warning
```

The warning was the known local `.pytest_cache` write-permission warning.

## Notes

Refreshing the editable install first required network access to resolve the build dependency. The approved rerun of `.venv/bin/python -m pip install -e .` completed successfully.
