# Semantic Planning Fallback v1 Retrospective

## What Changed

- Added CLI workflow as a first-class mission playbook and mission attribute.
- Added CLI-specific mission-contract generation for command routing, explicit subcommands, interactive assessment, structured answers, automatic initialization, Plan generation, assess compatibility, documentation, and tests.
- Replaced unsupported generic fallback behavior with an explicit insufficient-understanding path for low-confidence unknown missions.
- Updated assessment so vague unknown missions ask for more specific mission intent instead of reporting `UNDERSTOOD`.
- Updated Plan rendering so CLI workflow Plans avoid generic application/API/deployment language.
- Added regression coverage for the exact bare-command UX dogfood mission and the low-confidence unknown fallback.
- Added strict TDD coverage for structured human-decision regeneration fidelity before implementation.
- Added pre-generation validation for malformed and conflicting structured human answers.
- Updated CLI workflow contract generation so explicit human decisions can tighten parser errors, assess removal, and valid mission-start semantics without manually patching `.battalion/mission-plan.md`.

## Root Cause

The mission analyst fallback assumed that every unrecognized mission still required a generic software application contract. When a CLI UX mission was classified as `Unknown / Unknown`, Battalion emitted requirements such as application entrypoint, controlled request errors, deployment environment risk, and generic application tests. Those outputs were deterministic, but they were not grounded in the mission.

A second defect appeared after classification improved: human decisions clarified stricter UX semantics, but the contract generator still emitted the older permissive CLI Plan. That meant humans could provide correct structured decisions while the authoritative Plan failed to fully reflect them.

## Determinism Lesson

Determinism belongs in artifact structure, traceability, IDs, reproducible mappings, and validation. It does not replace semantic assessment. When Battalion does not understand a mission, deterministic generation must report uncertainty instead of producing precise-looking but unsupported requirements.

## Dogfooding Friction

The failed bare-command UX Plan was useful evidence because it showed that the Plan looked authoritative while being semantically wrong. This is more dangerous than an obvious failure because it can send an executor down the wrong path with false confidence.

The TDD pass caught the same class of defect in a narrower form: missing, malformed, and conflicting decision data must not be silently converted into authoritative requirements. Battalion should block planning clearly when the structured decision evidence is not trustworthy.

## Remaining Friction

- Shell quoting for multiline mission text remains a UX concern for terminal users.
- The next bare-command UX slice can now proceed from a regenerated Plan that explicitly removes `assess` from public routing and help.

## Recommendation

Proceed to the bare-command UX slice only from the regenerated CLI workflow Plan grounded in structured human decisions. Do not implement it from the prior generic application Plan or from a manually patched Plan.
