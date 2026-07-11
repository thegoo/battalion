# Templates

Templates are the future home for reusable Battalion artifact shapes.

Current generated artifacts include:

- mission context;
- assessment output;
- objective plans;
- dispatch packages;
- evidence reports;
- resolve packages.

Template work should preserve deterministic output and human readability. Templates must support the doctrine that Plans are authoritative execution artifacts and Evidence Reports compare execution artifacts against Plans.

Plan Template v1 is currently implemented by the deterministic `battalion plan` renderer and written to `.battalion/mission-plan.md`. It is not loaded from this directory yet.

No runtime template loader is introduced by this repository realignment.

This directory is architectural intent, not a current runtime template path or package boundary.
