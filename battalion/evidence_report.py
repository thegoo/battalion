import json
from pathlib import Path


EVIDENCE_REPORT_SCHEMA_VERSION = "battalion.evidence_report.v1"
EVIDENCE_REPORT_ARTIFACT_VERSION = "v1"
EVIDENCE_REPORT_LIFECYCLE_STATUS = "Completed"


def _clean(value):
    return " ".join(str(value or "").strip().split())


def _relative_path(path, project):
    try:
        return path.relative_to(project).as_posix()
    except ValueError:
        return str(path)


def _read_plan_review(workspace, review_path=None):
    project = workspace.parent
    candidate = review_path or workspace / "plan-review.json"
    if not candidate.is_absolute():
        candidate = project / candidate
    if not candidate.is_file():
        raise ValueError(f"Plan Review JSON not found: {candidate}")
    try:
        review = json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Plan Review JSON is invalid: {candidate}") from exc
    if review.get("schema_version") != "battalion.plan_review.v1":
        raise ValueError("Evidence Report v1 requires Plan Review v1 JSON.")
    return review, _relative_path(candidate, project)


def _finding_summary(items):
    return [
        {
            "requirement_id": item.get("requirement_id", "—"),
            "criterion": item.get("criterion", "—"),
            "evidence": item.get("evidence", []),
            "finding": _clean(item.get("finding")),
            "recommendation": _clean(item.get("recommendation")),
        }
        for item in items or []
    ]


def _deviation_summary(items):
    return [
        {
            "scope_item": item.get("scope_item", "—"),
            "evidence": item.get("evidence", "—"),
            "finding": _clean(item.get("finding")),
        }
        for item in items or []
    ]


def _advisory_recommendation(review):
    failed = len(review.get("does_not_match") or [])
    unable = len(review.get("could_not_verify") or [])
    deviations = len(review.get("out_of_scope_evidence") or [])
    if failed:
        return "Address failed findings before asking humans to accept the work."
    if deviations:
        return "Review deviations before accepting, deferring, or rejecting the work."
    if unable:
        return "Resolve unable-to-verify findings or ask humans to explicitly accept the remaining risk."
    return "Evidence supports human review of the implementation against the Plan."


def build_evidence_report(workspace, review_path=None):
    review, review_reference = _read_plan_review(workspace, review_path=review_path)
    matches = _finding_summary(review.get("matches"))
    failed = _finding_summary(review.get("does_not_match"))
    unable = _finding_summary(review.get("could_not_verify"))
    deviations = _deviation_summary(review.get("out_of_scope_evidence"))
    return {
        "schema_version": EVIDENCE_REPORT_SCHEMA_VERSION,
        "artifact_version": EVIDENCE_REPORT_ARTIFACT_VERSION,
        "lifecycle_status": EVIDENCE_REPORT_LIFECYCLE_STATUS,
        "lineage": {
            "mission": review.get("mission", "not recorded by Plan Review v1"),
            "plan": review.get("plan", "—"),
            "plan_version": review.get("plan_version", "not recorded"),
            "plan_review": review_reference,
            "plan_review_schema_version": review.get("schema_version", "—"),
        },
        "authoritative_status": "The latest non-superseded Evidence Report is authoritative; Evidence Report v1 does not implement a runtime resolver.",
        "summary": {
            "requirements_reviewed": len(review.get("requirements") or []),
            "evidence_files": len(review.get("evidence") or []),
            "verified": len(matches),
            "failed": len(failed),
            "unable_to_verify": len(unable),
            "deviations": len(deviations),
        },
        "verified_findings": matches,
        "failed_findings": failed,
        "unable_to_verify_findings": unable,
        "deviations": deviations,
        "open_assumptions": [],
        "open_risks": [],
        "assumption_risk_note": "Open assumptions and risks are not supplied by Plan Review v1.",
        "battalion_recommendation": _advisory_recommendation(review),
        "human_decision_boundary": [
            "Evidence Reports report facts and advisory recommendations.",
            "Humans decide whether to proceed, accept risk, defer, reject, merge, deploy, or approve work.",
            "This report does not approve, reject, merge, deploy, authorize execution, or gate work.",
            "Passing tests, implementation completion, and Battalion recommendations are never human approval.",
        ],
        "human_decision_evidence": review.get("human_decision_evidence") or [],
    }


def render_evidence_report(report):
    lines = [
        "# Evidence Report",
        "",
        "Evidence Reports summarize Plan Review facts for human decision-making. Humans make engineering decisions.",
        "",
        "## Metadata",
        "",
        f"- Schema version: {report['schema_version']}",
        f"- Artifact version: {report['artifact_version']}",
        f"- Lifecycle status: {report['lifecycle_status']}",
        f"- Authoritative status: {report['authoritative_status']}",
        "",
        "## Lineage",
        "",
        f"- Mission evaluated: {report['lineage']['mission']}",
        f"- Plan evaluated: {report['lineage']['plan']}",
        f"- Plan version: {report['lineage']['plan_version']}",
        f"- Plan Review consumed: {report['lineage']['plan_review']}",
        f"- Plan Review version: {report['lineage']['plan_review_schema_version']}",
        "",
        "## Summary",
        "",
    ]
    for label, key in (
        ("Requirements reviewed", "requirements_reviewed"),
        ("Evidence files", "evidence_files"),
        ("Verified", "verified"),
        ("Failed", "failed"),
        ("Unable to verify", "unable_to_verify"),
        ("Deviations", "deviations"),
    ):
        lines.append(f"- {label}: {report['summary'][key]}")
    lines.extend(["", "## Verified Findings", ""])
    lines.extend(_finding_lines(report["verified_findings"], "No verified findings were reported."))
    lines.extend(["", "## Failed Findings", ""])
    lines.extend(_finding_lines(report["failed_findings"], "No failed findings were reported."))
    lines.extend(["", "## Unable To Verify", ""])
    lines.extend(_finding_lines(report["unable_to_verify_findings"], "No unable-to-verify findings were reported."))
    lines.extend(["", "## Deviations", ""])
    if report["deviations"]:
        for item in report["deviations"]:
            lines.append(f"- {item['scope_item']}")
            lines.append(f"  - Evidence: {item['evidence']}")
            lines.append(f"  - Finding: {item['finding']}")
    else:
        lines.append("- No out-of-scope evidence was reported.")
    lines.extend(["", "## Open Assumptions, Risks, and Deviations", ""])
    lines.append(f"- Open assumptions: {len(report['open_assumptions'])}")
    lines.append(f"- Open risks: {len(report['open_risks'])}")
    lines.append(f"- Deviations: {len(report['deviations'])}")
    lines.append(f"- Note: {report['assumption_risk_note']}")
    lines.extend(["", "## Battalion Recommendation", ""])
    lines.append(f"- Advisory only: {report['battalion_recommendation']}")
    lines.extend(["", "## Human Decision Boundary", ""])
    lines.extend(f"- {item}" for item in report["human_decision_boundary"])
    lines.extend(["", "## Human Decision Evidence", ""])
    if report["human_decision_evidence"]:
        for item in report["human_decision_evidence"]:
            reference = f" Reference: {item['reference']}" if item.get("reference") else ""
            lines.append(f"- {item['label']} [{item['status']}]: {item['description']}{reference}")
    else:
        lines.append("- None recorded.")
    return "\n".join(lines).rstrip() + "\n"


def _finding_lines(items, empty):
    if not items:
        return [f"- {empty}"]
    lines = []
    for item in items:
        evidence = ", ".join(item["evidence"]) if item["evidence"] else "None"
        lines.append(f"- {item['requirement_id']}: {item['criterion']}")
        lines.append(f"  - Evidence: {evidence}")
        lines.append(f"  - Finding: {item['finding']}")
        lines.append(f"  - Recommendation: {item['recommendation']}")
    return lines


def write_evidence_report(workspace, review_path=None):
    report = build_evidence_report(workspace, review_path=review_path)
    markdown = render_evidence_report(report)
    (workspace / "evidence-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (workspace / "evidence-report.md").write_text(markdown, encoding="utf-8")
    return report, markdown
