# Objective Plan / Roadmap

This roadmap describes the product direction after Doctrine v1.0 realignment. It is intentionally objective-focused rather than slice-history-focused.

## Product objective

Battalion should help teams produce consistent engineering plans and evidence reports for human and executor-driven implementation.

## Current spine

1. Capture mission context.
2. Assess whether the mission is understood.
3. Produce an authoritative objective plan.
4. Dispatch the plan to a human or executor workflow.
5. Collect and compare evidence against the plan.
6. Produce resolve packages for failed engineering findings.

## Governing sequence

The governing product sequence is:

1. Core Foundation.
2. Mission Playbooks.
3. Assessment → Plan generation.
4. Plan Review.
5. Evidence Report.
6. Skill Layer.
7. Integrations.

The immediate product focus is strengthening the artifact pipeline around Plans, reviews, evidence, and human decisions. Artifact catalog strategy follows after the core artifacts are stable enough for Battalion to use on its own work.

## Near-term objectives

- Improve objective-plan quality while preserving deterministic output.
- Expand mission playbooks without expanding assessment beyond mission scope.
- Refine review signals so assurance findings are easier for humans to act on.
- Improve evidence report readability and traceability.
- Keep executor integrations thin and replaceable.

## Deferred until after the foundation is stable

- Runtime orchestration.
- Long-running process management.
- Model routing or model configuration.
- Project-wide architecture governance.
- Automatic repository modification outside explicit executor workflows.

## Versioning posture

Battalion remains pre-v1. Minor versions may refine workflow contracts, artifact structure, and terminology. A future `1.0.0` release should mark a stable public workflow and artifact contract.

Battalion doctrine treats material artifact changes as versioned history. The latest non-superseded artifact version is authoritative; older versions remain traceable records of prior rationale, evidence, and human decisions.
