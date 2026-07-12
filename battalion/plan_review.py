import json
import re
from pathlib import Path


REVIEW_SCHEMA_VERSION = "battalion.plan_review.v1"
REVIEW_QUESTIONS = (
    "What did the Plan require?",
    "What evidence exists?",
    "What matches?",
    "What does not match?",
    "What could not be verified?",
)
DECISION_SOURCES = {
    "pr-approval": {
        "label": "PR approval",
        "default_status": "PENDING",
        "description": "May satisfy human review evidence when observed.",
    },
    "pr-merge": {
        "label": "PR merge",
        "default_status": "PENDING",
        "description": "May satisfy authorization or completion evidence when observed.",
    },
    "manual-artifact": {
        "label": "Manual artifact update",
        "default_status": "OPTIONAL_FALLBACK",
        "description": "Optional fallback for workflows without a pull request.",
    },
}
DECISION_STATUSES = {
    "PENDING",
    "OBSERVED",
    "APPROVED",
    "EXECUTED",
    "MISSING",
    "UNABLE_TO_VERIFY",
    "OPTIONAL_FALLBACK",
}


def _clean(value):
    return " ".join(str(value).strip().split())


def _slug(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _contains_normalized(haystack, needle):
    return _slug(needle) in _slug(haystack)


def _requirement_reports_status(content, requirement_id, terms):
    status_terms = "|".join(sorted((re.escape(term) for term in terms), key=len, reverse=True))
    pattern = rf"^.*\b{re.escape(requirement_id)}\b\s*(?::|-)?\s*(?:{status_terms})\b.*$"
    return re.search(pattern, content, flags=re.IGNORECASE | re.MULTILINE) is not None


def parse_decision_evidence(values):
    records = []
    for raw_value in values or []:
        value = str(raw_value).strip()
        source, separator, remainder = value.partition("=")
        source = source.strip().lower().replace("_", "-")
        if source not in DECISION_SOURCES:
            expected = ", ".join(sorted(DECISION_SOURCES))
            raise ValueError(f"Unknown human decision source: {source or value}. Expected one of: {expected}.")
        status = DECISION_SOURCES[source]["default_status"]
        reference = ""
        if separator:
            status_text, reference_separator, reference_text = remainder.partition(":")
            status = status_text.strip().upper().replace("-", "_") or status
            reference = reference_text.strip() if reference_separator else ""
        if status not in DECISION_STATUSES:
            expected = ", ".join(sorted(DECISION_STATUSES))
            raise ValueError(f"Unknown human decision status for {source}: {status}. Expected one of: {expected}.")
        records.append({
            "source": source,
            "label": DECISION_SOURCES[source]["label"],
            "status": status,
            "reference": reference,
            "description": DECISION_SOURCES[source]["description"],
        })
    if records:
        return records
    return [{
        "source": "manual-artifact",
        "label": DECISION_SOURCES["manual-artifact"]["label"],
        "status": DECISION_SOURCES["manual-artifact"]["default_status"],
        "reference": "",
        "description": DECISION_SOURCES["manual-artifact"]["description"],
    }]


def parse_plan_requirements(plan_text):
    requirements = []
    current = None
    in_acceptance = False
    for raw_line in plan_text.splitlines():
        line = raw_line.rstrip()
        match = re.match(r"^###\s+(R-\d{3})(?:\s+[-—]\s*(.+))?$", line)
        if match:
            if current:
                requirements.append(current)
            current = {
                "id": match.group(1),
                "statement": _clean(match.group(2) or ""),
                "acceptance": [],
            }
            in_acceptance = False
            continue
        if current is None:
            continue
        if line.startswith("### "):
            in_acceptance = False
            continue
        statement = re.match(r"^- Statement:\s*(.+)$", line)
        if statement:
            current["statement"] = _clean(statement.group(1))
            in_acceptance = False
            continue
        if line == "- Acceptance Criteria:":
            in_acceptance = True
            continue
        if line.startswith("- ") and not line.startswith("  - "):
            in_acceptance = False
        if in_acceptance:
            criterion = re.match(r"^\s+-\s+(.+)$", line)
            if criterion:
                current["acceptance"].append(_clean(criterion.group(1)))
    if current:
        requirements.append(current)
    return requirements


def _read_evidence(project, references):
    evidence = []
    for reference in references or []:
        candidate = Path(reference).expanduser()
        if not candidate.is_absolute():
            candidate = project / candidate
        try:
            resolved = candidate.resolve()
            resolved.relative_to(project.resolve())
        except ValueError:
            evidence.append({
                "path": str(reference),
                "status": "UNABLE_TO_VERIFY",
                "summary": "Evidence path escapes the project.",
                "content": "",
            })
            continue
        if not candidate.is_file():
            evidence.append({
                "path": str(reference),
                "status": "UNABLE_TO_VERIFY",
                "summary": "Evidence file was not found.",
                "content": "",
            })
            continue
        try:
            content = candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            evidence.append({
                "path": str(reference),
                "status": "UNABLE_TO_VERIFY",
                "summary": "Evidence file is not UTF-8 text.",
                "content": "",
            })
            continue
        evidence.append({
            "path": candidate.relative_to(project).as_posix(),
            "status": "AVAILABLE",
            "summary": _clean(content[:240]) or "Evidence file is empty.",
            "content": content,
        })
    return evidence


def _classify_acceptance(requirement, criterion, evidence):
    if not evidence:
        return {
            "requirement_id": requirement["id"],
            "criterion": criterion,
            "result": "UNABLE_TO_VERIFY",
            "evidence": [],
            "finding": f"{requirement['id']}: No evidence was supplied for this acceptance criterion.",
            "recommendation": "Provide deterministic implementation or validation evidence.",
        }
    for item in evidence:
        content = item["content"]
        if item["status"] != "AVAILABLE":
            continue
        if _requirement_reports_status(content, requirement["id"], ("FAIL", "FAILED", "MISMATCH", "DOES_NOT_MATCH")):
            return {
                "requirement_id": requirement["id"],
                "criterion": criterion,
                "result": "DOES_NOT_MATCH",
                "evidence": [item["path"]],
                "finding": f"{requirement['id']}: Evidence reports a mismatch for this requirement.",
                "recommendation": "Correct the implementation or update the Plan through human review.",
            }
        if _contains_normalized(content, criterion) or _requirement_reports_status(content, requirement["id"], ("PASS", "PASSED", "MATCH", "VERIFIED")):
            return {
                "requirement_id": requirement["id"],
                "criterion": criterion,
                "result": "MATCHES",
                "evidence": [item["path"]],
                "finding": f"{requirement['id']}: Evidence supports this acceptance criterion.",
                "recommendation": "No action required.",
            }
    unavailable = [item for item in evidence if item["status"] != "AVAILABLE"]
    if unavailable and len(unavailable) == len(evidence):
        return {
            "requirement_id": requirement["id"],
            "criterion": criterion,
            "result": "UNABLE_TO_VERIFY",
            "evidence": [item["path"] for item in unavailable],
            "finding": f"{requirement['id']}: Evidence could not be read for this acceptance criterion.",
            "recommendation": "Provide readable source-controlled evidence.",
        }
    return {
        "requirement_id": requirement["id"],
        "criterion": criterion,
        "result": "UNABLE_TO_VERIFY",
        "evidence": [item["path"] for item in evidence if item["status"] == "AVAILABLE"],
        "finding": f"{requirement['id']}: Supplied evidence does not deterministically prove this acceptance criterion.",
        "recommendation": "Add evidence that directly maps to the requirement and criterion.",
    }


def review_plan(workspace, plan_path=None, evidence_paths=None, decision_evidence=None):
    project = workspace.parent
    plan = plan_path or workspace / "mission-plan.md"
    if not plan.is_absolute():
        plan = project / plan
    if not plan.is_file():
        raise ValueError(f"Authoritative Plan not found: {plan}")
    plan_text = plan.read_text(encoding="utf-8")
    requirements = parse_plan_requirements(plan_text)
    if not requirements:
        raise ValueError("Authoritative Plan contains no traceable requirements.")
    evidence = _read_evidence(project, evidence_paths or [])
    findings = []
    for requirement in requirements:
        acceptance = requirement.get("acceptance") or []
        if not acceptance:
            findings.append({
                "requirement_id": requirement["id"],
                "criterion": "Acceptance criteria",
                "result": "UNABLE_TO_VERIFY",
                "evidence": [],
                "finding": f"{requirement['id']}: Plan requirement has no acceptance criteria.",
                "recommendation": "Update the Plan before review can prove this requirement.",
            })
            continue
        for criterion in acceptance:
            findings.append(_classify_acceptance(requirement, criterion, evidence))
    out_of_scope = _out_of_scope_evidence(plan_text, evidence)
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "plan": str(plan.relative_to(project)) if plan.is_relative_to(project) else str(plan),
        "questions": list(REVIEW_QUESTIONS),
        "requirements": requirements,
        "evidence": [
            {"path": item["path"], "status": item["status"], "summary": item["summary"]}
            for item in evidence
        ],
        "matches": [item for item in findings if item["result"] == "MATCHES"],
        "does_not_match": [item for item in findings if item["result"] == "DOES_NOT_MATCH"],
        "could_not_verify": [item for item in findings if item["result"] == "UNABLE_TO_VERIFY"],
        "out_of_scope_evidence": out_of_scope,
        "human_decision_evidence": parse_decision_evidence(decision_evidence),
        "human_decision_inputs": [
            "Humans decide whether to proceed, accept risk, defer, reject, merge, deploy, or approve work.",
            "Plan Review findings and recommendations are advisory signals only.",
            "PR approval may satisfy human review evidence when observed.",
            "PR merge may satisfy authorization or completion evidence when observed.",
            "Manual artifact updates are optional fallback evidence for workflows without a pull request.",
            "Passing tests, implementation completion, and Battalion recommendations are never human approval.",
        ],
    }


def _out_of_scope_evidence(plan_text, evidence):
    match = re.search(r"^## Out of Scope\s*(.*?)(?:^## |\Z)", plan_text, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return []
    items = [line[2:].strip().rstrip(".") for line in match.group(1).splitlines() if line.startswith("- ")]
    results = []
    for item in items:
        for evidence_item in evidence:
            if evidence_item["status"] != "AVAILABLE":
                continue
            if _mentions_out_of_scope_work(evidence_item["content"], item):
                results.append({
                    "scope_item": item,
                    "evidence": evidence_item["path"],
                    "finding": f"Out-of-scope evidence references: {item}.",
                })
    return results


def _mentions_out_of_scope_work(content, item):
    normalized_item = re.escape(_slug(item))
    text = _slug(content)
    patterns = (
        rf"\b(added|implemented|created|changed|modified|built|introduced)\s+{normalized_item}\b",
        rf"\b{normalized_item}\s+(added|implemented|created|changed|modified|built|introduced)\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def render_plan_review(result):
    lines = [
        "# Plan Review",
        "",
        "Plan Review reports facts and advisory recommendations. Humans make engineering decisions.",
        "",
        f"- Plan: {result['plan']}",
        f"- Requirements reviewed: {len(result['requirements'])}",
        f"- Evidence files: {len(result['evidence'])}",
        "",
        "## What did the Plan require?",
        "",
    ]
    for requirement in result["requirements"]:
        lines.append(f"### {requirement['id']}")
        lines.append("")
        lines.append(f"- Statement: {requirement['statement']}")
        lines.append("- Acceptance Criteria:")
        if requirement.get("acceptance"):
            lines.extend(f"  - {item}" for item in requirement["acceptance"])
        else:
            lines.append("  - None recorded.")
        lines.append("")
    lines.extend(["## What evidence exists?", ""])
    if result["evidence"]:
        for item in result["evidence"]:
            lines.append(f"- {item['path']} [{item['status']}]: {item['summary']}")
    else:
        lines.append("- None supplied.")
    if result["out_of_scope_evidence"]:
        lines.append("- Out-of-scope evidence was observed:")
        lines.extend(f"  - {item['scope_item']} in {item['evidence']}" for item in result["out_of_scope_evidence"])
    lines.extend(["", "## What matches?", ""])
    lines.extend(_finding_lines(result["matches"], "No matching evidence was found."))
    lines.extend(["", "## What does not match?", ""])
    lines.extend(_finding_lines(result["does_not_match"], "No mismatching evidence was found."))
    lines.extend(["", "## What could not be verified?", ""])
    lines.extend(_finding_lines(result["could_not_verify"], "Every reviewed criterion had deterministic evidence."))
    lines.append("")
    lines.append("Human decision evidence:")
    for item in result["human_decision_evidence"]:
        reference = f" Reference: {item['reference']}" if item.get("reference") else ""
        lines.append(f"- {item['label']} [{item['status']}]: {item['description']}{reference}")
    lines.append("")
    lines.append("Human decision inputs:")
    lines.extend(f"- {item}" for item in result["human_decision_inputs"])
    return "\n".join(lines).rstrip() + "\n"


def _finding_lines(values, empty):
    if not values:
        return [f"- {empty}"]
    lines = []
    for item in values:
        lines.append(f"- {item['requirement_id']}: {item['criterion']}")
        lines.append(f"  - Evidence: {', '.join(item['evidence']) if item['evidence'] else 'None'}")
        lines.append(f"  - Finding: {item['finding']}")
        lines.append(f"  - Recommendation: {item['recommendation']}")
    return lines


def write_plan_review(workspace, plan_path=None, evidence_paths=None, decision_evidence=None):
    result = review_plan(
        workspace,
        plan_path=plan_path,
        evidence_paths=evidence_paths,
        decision_evidence=decision_evidence,
    )
    markdown = render_plan_review(result)
    (workspace / "plan-review.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (workspace / "plan-review.md").write_text(markdown, encoding="utf-8")
    return result, markdown
