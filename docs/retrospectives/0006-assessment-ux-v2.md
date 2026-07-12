# Assessment UX v2 Retrospective

## What Changed

- Collapsed first-run usage into `battalion assess "My requirement"`.
- Removed `init` and `clarify` from the public CLI command surface.
- Kept initialization and clarification reconciliation as internal implementation details.
- Made assessment interactive by default when human answers are required and stdin is interactive.
- Replaced Q-ID-driven human prompts with ordinal `Question 1 of N` prompts.
- Added automatic Plan generation at the end of successful assessment.
- Updated README and regression tests for the intent-first flow.

## Dogfooding Friction

- The original dogfood attempt failed before assessment because long inline text was treated as a path. That was a first-run product defect and became part of this slice.
- The previous command model exposed implementation phases instead of user intent. The new flow lets the user state the mission once and lets Battalion handle state, questions, assessment, and Plan generation.
- Internal Q-IDs remain useful for audit and traceability, but requiring humans to type them made the CLI feel like a database maintenance tool rather than an engineering assistant.
- The five-question cap needed to apply across all question sources, not separately to each assessment subsystem.
- Follow-up dogfooding found that answers were technically captured but semantically unsafe: the CLI appended full question text and examples into `mission_prompt`, so example prose became apparent mission intent. The concrete failure was a README answer flow where the "blank README" example contaminated reassessment.
- The fix moved human answers out of the mission prompt and into structured answer records. Assessment and contract generation can consume clean answer values, while the original human requirement remains unchanged as the mission source.

## Recommendations

- Keep watching first-run friction during normal software slices.
- Avoid exposing new commands unless they represent a user intent rather than an internal pipeline phase.
- Consider a future naming pass for `assure` versus `review`/`evidence-report`, but do not broaden this slice.
- Treat prompt examples as display-only UX. They must never become authoritative mission context unless the human selects or types them as an answer.
