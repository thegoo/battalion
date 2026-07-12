# Evidence Report v1 Validation Evidence

## Requirement Evidence

- R-001 PASS: `battalion evidence-report` reads `.battalion/plan-review.json` by default, writes `.battalion/evidence-report.md`, writes `.battalion/evidence-report.json`, and regression coverage verifies deterministic repeated output.
- R-002 PASS: Evidence Report v1 summarizes the Plan evaluated, Plan Review artifact consumed, verified findings, failed findings, unable-to-verify findings, and out-of-scope evidence as deviations.
- R-003 PASS: Markdown and JSON include Evidence Report schema version, artifact version, lifecycle status, Plan lineage, Plan Review schema version, and the latest non-superseded authoritative-status statement without adding a resolver.
- R-004 PASS: Evidence Report v1 includes the human-decision boundary, carries observed human decision evidence from Plan Review, keeps Battalion recommendations advisory, and does not approve, reject, merge, deploy, authorize execution, gate work, or infer approval from tests or implementation completion.
- R-005 PASS: README documents `battalion evidence-report`; regression tests cover generation, failed and unable-to-verify findings, deviations, lineage, and human-authority language; this evidence file and `docs/retrospectives/0005-evidence-report-v1.md` record dogfooding evidence and friction.
- Dogfood refresh PASS: Plan Review was regenerated against `docs/plans/0005-evidence-report-v1.md` using `docs/evidence/0005-evidence-report-v1.md`, then Evidence Report was regenerated from that Plan Review. The refreshed Evidence Report lineage references Evidence Report v1 and reports 26 verified findings, 0 failed findings, 0 unable-to-verify findings, and 0 deviations.
- Defect fix PASS: Dogfooding exposed that Plan Review status detection treated later words such as "failed findings" as requirement failure signals after an earlier `R-001 PASS` marker. Status detection is now scoped to explicit requirement status markers, and regression coverage prevents recurrence.

## Validation Commands

```bash
python3 -m pytest tests/test_cli.py -k evidence_report
python3 -m pytest tests/test_cli.py -k "plan_review_status_detection or plan_review_covers_mismatch or evidence_report"
python3 -m pytest
python3 -m battalion.cli review --plan docs/plans/0005-evidence-report-v1.md --evidence docs/evidence/0005-evidence-report-v1.md
python3 -m battalion.cli evidence-report
```

## Validation Results

```text
tests/test_cli.py -k evidence_report: 2 passed, 176 deselected, 1 warning
tests/test_cli.py -k "plan_review_status_detection or plan_review_covers_mismatch or evidence_report": 4 passed, 174 deselected, 1 warning
python3 -m pytest: 178 passed, 1 warning in 18.92s
python3 -m battalion.cli review --plan docs/plans/0005-evidence-report-v1.md --evidence docs/evidence/0005-evidence-report-v1.md: generated .battalion/plan-review.md and .battalion/plan-review.json with 26 matches, 0 mismatches, and 0 unable-to-verify findings
python3 -m battalion.cli evidence-report: generated .battalion/evidence-report.md and .battalion/evidence-report.json with lineage to docs/plans/0005-evidence-report-v1.md, 26 verified findings, 0 failed findings, 0 unable-to-verify findings, and 0 deviations
```

Warning: pytest could not write `.pytest_cache` because of local sandbox permissions. This did not affect test execution.

## Human Decision Evidence

Human approval, PR approval, PR merge, or explicit deferral remains pending outside Battalion recommendations.
