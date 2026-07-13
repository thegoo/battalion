# Development Workflow

This workflow keeps Battalion buildable, runnable, and aligned with Doctrine v1.0.

## Install for development

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
battalion --help
```

## Run tests

Use the Python environment where Battalion was installed:

```bash
python -m pytest
```

The test suite is deterministic and should not require network access.

## Validate the CLI manually

From any scratch directory:

```bash
battalion "Describe the mission"
battalion "Create a README.md"
battalion "Create README.md and CONTRIBUTING.md"
battalion --ai-assisted-intake "Describe a larger ambiguous mission"
battalion plan
battalion assure
```

Battalion should create `.battalion` automatically on a quoted mission requirement.
Default intake is deterministic and no-AI. Use `--ai-assisted-intake` only when Battalion refuses a larger or ambiguous mission and recommends the opt-in path.

## Documentation expectations

Product documentation should describe current behavior and doctrine. Slice history belongs in `CHANGELOG.md`, not the README.

When adding or changing artifacts, preserve:

- deterministic output;
- human-readable serialization;
- evidence traceability;
- executor-agnostic language;
- separation between Assessment, Planning, Assurance, Dispatch, and Resolve.

## Engineering boundary

Battalion owns the WHAT. Executors own the HOW.

Implementation changes should not make Assessment responsible for architecture readiness, Assurance responsible for planning, or Dispatch responsible for executor configuration.
