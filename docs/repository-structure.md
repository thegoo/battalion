# Repository Structure

Battalion is organized around Doctrine v1.0 concepts while preserving the existing Python package layout for pre-v1 compatibility.

```text
doctrine/        Product doctrine and operating principles.
playbooks/       Human-facing playbook documentation and future external playbook assets.
templates/       Human-facing artifact template documentation and future template assets.
review-signals/  Review-signal documentation and future signal catalogs.
skills/          Human/executor skill guidance and future reusable skill assets.
docs/            Product and contributor documentation.
src/             Reserved source-layout target; see src/README.md.
battalion/       Current Python runtime package.
examples/        Example Battalion mission workspaces.
tests/           Deterministic regression tests.
```

The top-level concept directories are architectural intent and documentation surfaces. They are not current runtime package boundaries, import roots, or catalog search paths unless a specific document says otherwise.

## Why `battalion/` remains the runtime package

The existing package is already importable, installable, and covered by tests. Moving it into a `src/` layout would create packaging churn without improving Doctrine v1.0 alignment.

The top-level `src/` directory documents the future source-layout target. A physical package migration should be handled as a dedicated compatibility slice if the project needs it.

## Artifact locations

Packaged runtime catalogs currently live inside `battalion/` so editable and installed CLI execution both work:

- `battalion/attributes.yml`
- `battalion/playbooks.yml`

Top-level folders describe product architecture and future extension surfaces. They are not currently runtime search paths or package boundaries unless explicitly documented.
