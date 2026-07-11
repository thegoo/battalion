# Repository Realignment Report

## Summary

The repository has been realigned around Battalion Doctrine v1.0 without rewriting working functionality.

The new repository structure now exposes doctrine, playbooks, templates, review signals, skills, docs, source-layout guidance, runtime code, and examples as distinct concerns. Runtime code remains in the existing `battalion/` package to preserve import stability, editable installation behavior, and Git history.

The documentation now reinforces the current product philosophy:

- Battalion owns the WHAT.
- Executors own the HOW.
- Battalion reports facts.
- Humans make engineering decisions.
- Plans are authoritative execution artifacts.
- Evidence Reports compare execution artifacts against Plans.
- Battalion remains boring.
- Battalion eats its own dogfood.

## Kept

- `battalion/` runtime package: retained because the CLI is already runnable, packaged, and tested from this location.
- `battalion/attributes.yml`: retained as the packaged mission classification catalog required by installed CLI execution.
- `battalion/playbooks.yml`: retained as the packaged assessment playbook catalog required by installed CLI execution.
- `examples/`: retained as the current example mission workspace surface.
- `tests/`: retained as the deterministic regression suite.
- Existing command spine: retained because it already reflects mission context, assessment, planning, dispatch, assurance, resolve, and reporting.

## Refactored

- Added `doctrine/` with Doctrine v1.0 principles and phase boundaries.
- Added `docs/ROADMAP.md` to describe the objective product plan without turning the README into implementation history.
- Added `docs/repository-structure.md` to explain the realigned repository and why runtime code remains in `battalion/`.
- Added `docs/development-workflow.md` to document install, test, CLI validation, and doctrine-preserving contribution expectations.
- Added top-level `playbooks/`, `templates/`, `review-signals/`, and `skills/` documentation surfaces.
- Added `src/README.md` to reserve the future source-layout target while deferring physical package migration.
- Updated packaging compatibility metadata in `setup.py` so the editable-install shim matches the current `pyproject.toml` package version and packaged data files.
- Updated README language to describe Battalion as a deterministic engineering planning and evidence system rather than an AI workflow tool.

## Removed

- No tracked runtime functionality was removed.
- No tracked source files were deleted.
- No Git history was rewritten.

Obsolete concepts were addressed through documentation and terminology realignment rather than deletion because the current implementation still contains reusable mission assessment, planning, evidence, dispatch, assurance, and resolve behavior.

## Deferred

- Moving the Python package into `src/battalion` is deferred to a focused packaging compatibility slice.
- Moving packaged catalogs from `battalion/*.yml` into top-level product directories is deferred until runtime catalog discovery supports installed-package and external catalog paths.
- Deeper terminology cleanup inside internal module names is deferred where renaming would create unnecessary churn.
- Legacy assessment artifact fields and compatibility tests that still use earlier readiness or implementation recommendation language are deferred to a focused artifact-contract migration because changing them now would modify behavior beyond repository realignment.
- Runtime orchestration, model routing, executor lifecycle management, and long-running process control remain out of scope.
- Formal external template and review-signal catalogs remain future work.

## Risks

- The repository now contains both top-level product concept directories and packaged runtime catalogs under `battalion/`; documentation explains that the top-level directories are architectural intent, not current runtime package boundaries, but future contributors may still expect top-level catalogs to be runtime-loaded.
- Internal module names still reflect earlier implementation history in places. Renaming them now would risk broad churn.
- The editable-install compatibility shim in `setup.py` can drift from `pyproject.toml` unless guarded by tests.
- The pre-v1 workflow is still evolving, so documentation must continue to distinguish stable doctrine from changing implementation details.
- Some internal compatibility surfaces still preserve pre-Doctrine terminology to avoid breaking existing tests and artifacts during this architecture-only slice.

## Recommendations

The next Battalion slice should establish Plan Template v1 / Dogfooded Plan Artifact.

Recommended scope:

- define the authoritative Plan template well enough for Battalion to use it on Battalion work;
- dogfood the Plan artifact on the next implementation slice;
- prove that the Plan can carry objective, acceptance, evidence, and review expectations without relying on conversational context;
- keep human decision ownership explicit in the Plan and review flow;
- record any gaps that should become Evidence Report or template follow-up work.

The following slice should establish a first-class artifact catalog strategy.

Recommended catalog-strategy scope:

- define how packaged defaults and repository-level overrides are discovered;
- decide whether playbooks, attributes, templates, and review signals move out of `battalion/`;
- keep installed CLI behavior deterministic;
- preserve human-readable YAML artifact contracts;
- add tests proving installed-package catalog discovery works from arbitrary directories.

This would let the new repository structure become executable architecture rather than documentation-only architecture.
