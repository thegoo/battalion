# Evidence: Example vs Requested Artifact Disambiguation v1

## Mission

Fix mission intake so artifact names used as examples are not treated as requested deliverables.

## Failed Dogfood Evidence

Clean `.battalion` dogfood command:

```text
battalion "Fix mission intake so artifact names used as examples are not treated as requested deliverables. For example, in a requirement like 'When a mission asks for multiple documentation artifacts such as README.md and CONTRIBUTING.md, assessment labels should match the structured intake,' README.md and CONTRIBUTING.md are example artifacts for a test case, not files to create. Battalion should distinguish requested artifacts from examples, preserve traceability, and generate a Plan for the actual requested behavior. Direct requests like 'Create README.md and CONTRIBUTING.md' must still produce documentation deliverables for both files."
```

Observed bad result:

- Mission Type: Documentation / README
- Mission Intent: Create a README.md file.
- Understanding incorrectly listed README.md and CONTRIBUTING.md as distinct documentation artifacts to create.
- No authoritative Plan was produced.

## Corrected Behavior

- `such as README.md and CONTRIBUTING.md` records README.md and CONTRIBUTING.md as example references, not requested artifacts.
- `for example README.md and CONTRIBUTING.md` records README.md and CONTRIBUTING.md as example references, not requested artifacts.
- `e.g. README.md and CONTRIBUTING.md` records README.md and CONTRIBUTING.md as example references, not requested artifacts.
- `Create README.md and CONTRIBUTING.md` still records both files as requested artifacts and generates documentation requirements for both.
- Original mission text remains unchanged in `mission.yaml`.

## Test Evidence

Focused red before implementation:

```text
python3 -m pytest tests/test_cli.py -k "example_artifacts_after or compound_docs_mission_preserves_distinct_requested_artifacts or compound_docs_questions_are_not_readme_only"
3 failed, 2 passed, 198 deselected
```

Expected failure reason:

```text
ledger["intake"]["requested_artifacts"] contained README.md and CONTRIBUTING.md for example-only prompts.
```

Focused green after implementation:

```text
python3 -m pytest tests/test_cli.py -k "example_artifacts_after or compound_docs_mission_preserves_distinct_requested_artifacts or compound_docs_questions_are_not_readme_only"
5 passed, 198 deselected
```
