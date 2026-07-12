# Artifact Lifecycle and Versioning v1 Dogfooding Retrospective

## Plan Used

- `docs/plans/0004-artifact-lifecycle-versioning-v1.md`

## What Changed

- Added doctrine for Draft, Approved, Completed, and Superseded artifact lifecycle states.
- Defined Completed as fulfillment of the artifact's mission-lifecycle role.
- Defined Superseded as replacement by a newer authoritative version.
- Added doctrine that material updates should create new versions rather than overwrite history.
- Added source-of-truth doctrine: latest non-superseded version is authoritative, while older versions remain traceable historical records.
- Updated roadmap wording so it no longer points at Plan Template v1 as the immediate authorized slice.

## Friction

- The initial generated `.battalion/mission-plan.md` was too generic because assessment recorded the requirement file path as the mission prompt. The durable Plan for this slice was therefore written explicitly from the approved doctrine requirements rather than changing CLI behavior inside this doctrine-only slice.
- The lifecycle wording needed to avoid implying a storage model. Terms such as manifest, resolver, and mission record remain future implementation concerns.

## Recommendation

- Treat artifact lifecycle/versioning as doctrine now and defer resolver or mission-record mechanics until a later implementation slice has its own Plan.
