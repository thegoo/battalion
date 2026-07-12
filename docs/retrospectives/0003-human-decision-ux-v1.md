# Human Decision UX v1 Dogfooding Retrospective

## Plan Used

- `docs/plans/0003-human-decision-ux-v1.md`

## What Changed

- Added structured decision-source evidence to Plan Review.
- Added CLI reporting for PR approval, PR merge, and manual artifact fallback statuses.
- Updated Plan Template language so manual artifact edits are not the default human-decision completion mechanism.
- Updated README guidance for PR-based decision evidence.
- Added deterministic regression tests for the new UX semantics.

## Friction

- Automatic GitHub inspection would make PR approval and merge detection smoother, but it would broaden this slice into integration behavior. The v1 UX stays local and deterministic by accepting observed decision evidence explicitly.
- The phrase "decision evidence" is more precise than "decision record" for this workflow because the authoritative human act can be a repository event rather than a Markdown edit.

## Recommendation

- Keep Human Decision UX v1 as a local reporting contract. A later integration slice may observe GitHub PR events directly, but Battalion should still report the source and status rather than approving or merging anything itself.
