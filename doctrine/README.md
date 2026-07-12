# Battalion Doctrine v1.0

Battalion is a deterministic engineering planning and evidence system.

It exists to standardize the artifacts that guide implementation and review. Battalion does not own engineering judgment, runtime strategy, model selection, deployment authority, or approval by assertion.

## Core doctrine

- Battalion owns the WHAT.
- Executors own the HOW.
- Battalion reports facts.
- Humans make engineering decisions.
- Plans are authoritative execution artifacts.
- Evidence Reports compare execution artifacts against Plans.
- Battalion remains boring.
- Battalion eats its own dogfood.

## Mission-first boundary

The mission is the source of authority. Battalion must not expand a mission into unrelated architecture, deployment, framework, runtime, or project-wide obligations unless the mission requires those concerns.

Assessment asks:

> Do we understand this mission well enough to create a plan?

Planning asks:

> What deterministic execution artifact should guide the work?

Assurance asks:

> Does the completed work satisfy the authoritative plan and evidence expectations?

Execution asks:

> How should the requested work be implemented?

Battalion intentionally stops before answering the last question. Humans or selected executors own implementation choices.

## Boring by design

Battalion should prefer deterministic files, explicit contracts, source-controlled records, and simple command behavior over orchestration theater or clever automation. New capabilities should make planning and evidence easier to trust, not more magical.

## Eat our own dogfood

Battalion should use its own Plans and Evidence Reports to define, execute, and review Battalion work. Dogfooding is how the project proves that its artifacts are authoritative enough for real engineering decisions.

## Dogfooding over speculation

Friction discovered through real dogfooding outranks speculative roadmap work when it blocks use, corrupts mission intent, weakens evidence, or materially increases human effort.

Dogfooding findings should be evaluated against mission impact and may supersede planned roadmap sequencing. Battalion should not chase every cosmetic issue, but real workflow friction is product evidence, not noise.

## Evidence over assertion

Claims do not complete work. Battalion records acceptance criteria, required evidence, reviews, findings, and assurance results so completed work can be compared against the plan.

Mission Assurance must prefer observable evidence over source-visible intent when runtime evidence is available. Diagnostics may explain likely causes, but they do not override evidence.

## Artifact lifecycle and versioning

Battalion artifacts move through explicit lifecycle states:

- Draft: the artifact is being prepared and is not yet authoritative.
- Approved: humans have accepted the artifact as authoritative for its role.
- Completed: the artifact fulfilled its role in the mission lifecycle.
- Superseded: a newer authoritative version exists.

Completed is a valid terminal state for an artifact that did its job. Archived is not the normal terminal state for completed artifacts; supersession records that a newer version has replaced the prior authoritative version.

Material updates should create new artifact versions rather than overwrite history. In principle, a material update should flow through assessment, plan, implementation, evidence, review, and human decision again.

The latest non-superseded version is the source of truth. Older versions remain part of the traceable historical record so evolution, rationale, evidence, and human decisions are preserved instead of erased.

## Determinism

Battalion artifacts should be reproducible, source-controlled, human-readable, and truthful to their declared serialization format.

- `.yaml` artifacts are proper YAML.
- `.json` artifacts are proper JSON.
- `.jsonl` artifacts are JSON Lines.

Deterministic output is a product requirement because the plan and evidence report are engineering records, not conversational byproducts.

## Executor-agnostic operation

Battalion may dispatch a plan or resolve package to an executor, but executor lifecycle remains outside Battalion.

Battalion does not:

- install executors;
- configure models;
- authenticate tools;
- choose implementation strategy;
- weaken acceptance criteria;
- approve work by self-report.

## Doctrine-guided workflow

```text
Mission Context
↓
Assessment
↓
Objective Plan
↓
Dispatch / Human Execution
↓
Evidence Report
↓
Resolve, if failures remain
↓
Evidence Report
```

The workflow is complete only when evidence supports the plan and humans accept the engineering decision.
