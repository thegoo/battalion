# Dogfooding Friction Doctrine v1 Validation Evidence

## Requirement Evidence

- R-001 PASS: `doctrine/README.md` adds "Dogfooding over speculation," stating that friction discovered through real dogfooding outranks speculative roadmap work when it blocks use, corrupts mission intent, weakens evidence, or materially increases human effort. It also states that findings may supersede planned roadmap sequencing when evaluated against mission impact.
- R-002 PASS: Existing doctrine remains intact, including boring design, evidence over assertion, human decision ownership, authoritative Plans, and dogfooding. The new principle does not assign approval, implementation strategy, or decision authority to Battalion.
- R-003 PASS: This evidence artifact and `docs/retrospectives/0007-dogfooding-friction-doctrine-v1.md` were produced for the slice.
- R-004 PASS: Local run guidance was inspected in `README.md`, `pyproject.toml`, and `setup.py`. The installed console script is `battalion = battalion.cli:main`; the documented local setup is a Python virtual environment plus editable install from the repository root.

## Dogfood Findings

- Battalion generated an authoritative `.battalion/mission-plan.md` for this doctrine mission without requiring human answers.
- The generated Plan was too generic for a doctrine-only documentation slice and included application-entrypoint requirements. The source-controlled Plan for this slice was tightened manually while preserving the dogfood output as evidence of friction.
- This finding supports the doctrine change: real dogfooding exposed material planning friction that is more important than speculative roadmap work.

## Validation Commands

```bash
python -m pytest
```

## Validation Results

```text
180 passed in 25.77s
```

## Human Decision Evidence

Human approval, PR approval, PR merge, or explicit deferral remains pending outside Battalion recommendations.
