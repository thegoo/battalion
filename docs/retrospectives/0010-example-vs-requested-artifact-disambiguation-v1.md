# Retrospective: Example vs Requested Artifact Disambiguation v1

## What Changed

Battalion now distinguishes Markdown artifact names used as examples from Markdown artifact names requested as deliverables during deterministic intake. Assessment and mission contract generation consume the same requested-artifact extraction path so labels, persisted intake, and generated requirements stay aligned.

## Lesson

Named entities in requirements may be examples, not requested work. Deterministic intake must preserve the human's original words while still identifying whether a named artifact is a deliverable, an example reference, or unsafe to infer.

## Follow-Up Signals

- Keep direct compound-document requests covered by regression tests.
- Expand disambiguation only when concrete language patterns are known.
- Prefer asking or stopping when artifact intent is ambiguous instead of silently treating every filename as work to create.
