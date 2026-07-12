# Dogfooding Friction Doctrine v1 Retrospective

## What Changed

- Added a concise doctrine principle that real dogfooding friction can outrank speculative roadmap work.
- Scoped the principle to material friction: blocked use, corrupted mission intent, weakened evidence, or materially increased human effort.
- Preserved the existing doctrine that Battalion remains boring, reports evidence, treats Plans as authoritative, and leaves decisions to humans.

## Dogfooding Friction

- Battalion successfully accepted the doctrine mission through the current `battalion assess` flow and generated a Plan without questions.
- The generated Plan treated the doctrine update like a generic implementation mission and included irrelevant application-entrypoint requirements.
- The slice therefore used Battalion's generated Plan as the dogfood starting point, then produced a tighter source-controlled Plan that better represented the doctrine-only work.

## Recommendations

- Treat this as evidence that documentation/doctrine missions need sharper assessment and planning behavior in a future slice.
- Do not broaden this doctrine slice into assessment-template work.
- Continue allowing real dogfooding friction to interrupt roadmap sequencing when it materially affects first-run usability, mission intent, evidence quality, or human effort.
