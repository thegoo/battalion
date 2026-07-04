# Changelog

All notable Battalion changes are summarized here. Product usage documentation lives in [README.md](README.md).

## Unreleased

### Documentation

- Rewrote `README.md` as product documentation rather than implementation history.
- Moved release and slice summaries into `CHANGELOG.md`.

## v0.6.0 — Mission Assurance MVP

### Added

- Added engineering-contract assurance as the primary Mission Assurance output.
- Added per-acceptance-criterion assurance checks with `VERIFIED`, `FAILED`, and `UNABLE_TO_VERIFY` results.
- Added canonical `.battalion/assurance.json` output.
- Added human-readable `.battalion/assurance.md` output.
- Added deterministic observable checks for static evidence, response-body literals, endpoint references, HTTP 200 evidence, timestamps, Docker evidence, and test artifacts.
- Added health endpoint mismatch coverage where the contract requires `status = Healthy` and implementation evidence returns `status = ok`.

### Changed

- Separated engineering findings from governance findings.
- Overall assurance status is derived from engineering failures first, while preserving governance validation.
- CLI assurance output now prioritizes actionable engineering findings before governance findings.

## v0.5.0 — Dispatch MVP

### Added

- Added executor handoff dispatch via `battalion dispatch --executor`.
- Added supported executor IDs:
  - `codex`
  - `claude-code`
  - `copilot`
- Added executor-specific dispatch packages under `.battalion/dispatches/DSP-###/`.
- Added dispatch metadata recording.
- Added executor startup banner, output forwarding, heartbeat feedback, completion summary, and failure summary.
- Added `--mode auto` for local implementation work while preserving source-control and deployment boundaries.

### Changed

- Clarified that Dispatch assigns the mission and waits for executor completion, while executor strategy remains owned by the selected executor.
- Preserved `.battalion/mission-plan.md` as immutable engineering truth during dispatch.

## Infrastructure Cleanup — Standardize Artifact Serialization

### Changed

- Replaced JSON-formatted `.yaml` artifacts with proper YAML serialization.
- Switched YAML reads and writes to PyYAML.
- Removed the custom attribute-catalog YAML parser.
- Added literal block scalar serialization for multiline strings such as mission prompts.
- Added artifact serialization doctrine.
- Updated local test guidance to use the Python environment that installed Battalion.

### Validation

- Added tests proving generated `.yaml` artifacts are proper YAML, parseable, deterministic, and semantically preserved.
- Added regression coverage for multiline YAML block formatting.

## v0.4.2 — Planning UX & Engineering Specification Polish

### Changed

- Refined generated `mission-plan.md` readability.
- Improved readiness, risk, assumption, traceability, implementation guidance, testing strategy, evidence, and success-criteria presentation.
- Kept planning deterministic and mission-first.

## v0.4.1 — Mission-First Planning

### Changed

- Reworked planning output to optimize for the quality of the generated engineering specification.
- Improved background, objective, business outcome, functional requirements, implementation guidance, work breakdown, testing strategy, and mission success criteria.
- Avoided inventing unknown requirements.

## v0.4.0 — Planning Engine MVP

### Added

- Added assessment-gated Mission Planning.
- Added generation of `.battalion/mission-plan.md`.
- Added support for architecture reference filenames via `battalion plan --architecture`.

### Changed

- Planning consumes mission, assessment, assumptions, risks, resolved clarifications, and architecture reference filenames.
- Planning refuses `NOT_READY` and `PARTIALLY_READY` missions.

## v0.3.x — Mission Assessment and Classification

### Added

- Added Mission Assessment as the front door of Battalion.
- Added deterministic readiness evaluation and recommendation output.
- Added assessment JSON and Markdown artifacts.
- Added Mission Classification with configurable attribute catalog.
- Added classification evidence, source labels, hit counts, thresholds, and decisions.
- Added engineering compatibility disclaimer.

### Changed

- Separated assessment from clarification by default.
- Added `battalion assess --interactive` as an explicit convenience workflow.
- Improved assessment consistency, readiness quality, and classification explainability.

## v0.2.x — Dispatcher Runtime Skeleton

### Added

- Added first-class runtime assignments.
- Added assignment lifecycle states.
- Added scoped assignment context.
- Added result packets and abort packets.
- Added `battalion dispatch`, `battalion execute`, and `battalion status` runtime commands.
- Added assignment persistence through `BLOCKED` and `WAITING` remediation.

### Changed

- Dispatcher became the only authority allowed to advance runtime assignment state.
- Requirement owner, required reviews, lifecycle state, and evidence drive assignment ordering.
- `COMPLETE` without evidence blocks rather than completing work.

## v0.1.x — Mission Contract and CLI Foundation

### Added

- Added Mission Contract Enforcement.
- Added requirement acceptance criteria, evidence, assumptions, risks, required reviews, owner, and traceability support.
- Added audit validation.
- Added clarification artifacts and clarification resolution workflow.
- Added portable CLI execution through the `battalion` console entry point.

### Changed

- Mission Assurance can no longer return `GREEN / GO` without required acceptance criteria, evidence, reviews, valid audit trail, and traceable findings.
- `GO` is structurally impossible unless status is `GREEN`.
- CLI commands locate mission workspaces from the current directory instead of depending on repository root.
