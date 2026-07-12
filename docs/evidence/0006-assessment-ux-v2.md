# Assessment UX v2 Validation Evidence

## Requirement Evidence

- R-001 PASS: `battalion assess "My requirement"` is now the visible first-run command. It creates `.battalion` state when needed, avoids `File name too long` crashes for long inline requirement text, writes assessment artifacts, and writes `.battalion/mission-plan.md` when assessment is complete.
- R-002 PASS: Interactive assessment now asks required questions by ordinal label, captures answers immediately, persists clarification answers through the existing audited ledger model, reruns assessment, and does not require Q-ID input in the human-facing flow.
- R-003 PASS: `battalion assess` prompts once for a requirement when no mission exists and stdin is interactive. Non-interactive use without a mission returns actionable guidance.
- R-004 PASS: Requirement-level questions and contract clarification questions share one five-question budget per assessment run; regression coverage verifies the CLI does not present a sixth question.
- R-005 PASS: Public parser routing and help no longer expose `init` or `clarify`. README no longer presents them as supported first-run user journeys. Internal functions remain only as implementation helpers for existing storage and reconciliation behavior.
- R-006 PASS: README documents the intent-first assessment flow; regression tests cover inline zero-question assessment, multiple interactive questions, omitted requirement prompting, automatic initialization, Plan generation, five-question cap, and old command removal.

## Dogfood Findings

- The first attempted dogfood command failed immediately because long inline requirement text was interpreted as a filesystem path and raised `OSError: [Errno 63] File name too long`. This was fixed as part of R-001.
- The existing generated Plan for this slice was too generic for CLI UX work, so the durable source-controlled Plan was tightened from the generated artifact while preserving doctrine, traceability, and dogfood findings.
- A focused regression test exposed that assessment could ask five requirement questions and then continue into contract clarification questions in the same run. A shared per-run question budget fixed that issue.
- Follow-up dogfooding exposed that captured human answers were appended back into `mission_prompt` with full question and example prose. README examples included "blank README", so reassessment could infer the wrong intent and generate generic application-entrypoint requirements. This was fixed by preserving the original mission prompt, storing human answers as structured `human_answers`, and using only answer values as assessment context.
- The refreshed README dogfood run for `battalion assess "Create a README."` captured answers for project overview/setup instructions, external contributors, and lightweight-but-useful depth. The regenerated Plan produced contributor-facing README requirements and did not include blank README intent or application-entrypoint requirements.

## Validation Commands

```bash
python3 -m pytest tests/test_cli.py -q
```

## Validation Results

```text
180 passed, 1 warning in 29.20s
```

The warning was the known local `.pytest_cache` write-permission warning.

Focused regression validation:

```text
python3 -m pytest tests/test_cli.py::BattalionCliTests::test_assess_readme_answers_do_not_pollute_reassessment_with_examples -q
1 passed
```

Nearby Assessment UX validation:

```text
python3 -m pytest tests/test_cli.py -q -k "assess_readme or assessment_ux or omitted_requirement or first_run or question_cap or old_command or clarify or init"
6 passed, 174 deselected
```

## Human Decision Evidence

Human approval, PR approval, PR merge, or explicit deferral remains pending outside Battalion recommendations.
