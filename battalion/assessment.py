"""Deterministic mission assessment and engineering readiness evaluation."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from .storage import read_yaml


SCHEMA_VERSION = "battalion.assessment.v1"
READINESS_LEVELS = ("NOT_READY", "PARTIALLY_READY", "READY_WITH_RISK", "READY")
RECOMMENDATIONS = (
    "Resolve Clarifications",
    "Refine Requirements",
    "Perform Architecture Review",
    "Perform Security Review",
    "Complete Mission Planning",
    "Proceed to Implementation",
)


OBLIGATION_PACKS: Dict[str, List[Dict[str, Any]]] = {
    "Mission Analyst": [
        {
            "name": "Clarifications resolved",
            "applies_when": [],
            "required_disposition": "satisfied",
            "description": "All mission clarification questions are resolved, superseded, or rejected.",
            "severity": "High",
            "checker": "clarifications_resolved",
            "finding_message": "Resolve open clarifications before implementation begins.",
        },
        {
            "name": "Risks documented",
            "applies_when": [],
            "required_disposition": "satisfied",
            "description": "Mission risks are documented for human review.",
            "severity": "Medium",
            "checker": "risks_documented",
            "finding_message": "Document mission risks before implementation begins.",
        },
        {
            "name": "Assumptions documented",
            "applies_when": [],
            "required_disposition": "satisfied",
            "description": "Mission assumptions are documented for human review.",
            "severity": "Medium",
            "checker": "assumptions_documented",
            "finding_message": "Document mission assumptions before implementation begins.",
        },
    ],
    "Architect": [
        {
            "name": "Technology stack identified",
            "applies_when": [],
            "required_disposition": "satisfied",
            "description": "Implementation technology or framework selection is identified.",
            "severity": "High",
            "checker": "technology_stack_identified",
            "finding_message": "Identify implementation technology before implementation begins.",
        },
        {
            "name": "Application boundary identified",
            "applies_when": [],
            "required_disposition": "satisfied",
            "description": "The application boundary or executable entrypoint is identified.",
            "severity": "Medium",
            "checker": "application_boundary_identified",
            "finding_message": "Identify the application boundary before implementation begins.",
        },
        {
            "name": "API contract identified",
            "applies_when": ["REST_API", "PUBLIC_API", "PUBLIC_ENDPOINT"],
            "required_disposition": "satisfied",
            "description": "API behavior, endpoint, or contract information is identified.",
            "severity": "High",
            "checker": "api_contract_identified",
            "finding_message": "Define the API contract before implementation begins.",
        },
    ],
    "SecOps": [
        {
            "name": "Authentication dispositioned",
            "applies_when": ["AUTHENTICATION", "PUBLIC_API", "PUBLIC_ENDPOINT"],
            "required_disposition": "satisfied",
            "description": "Authentication requirements are identified or explicitly not applicable.",
            "severity": "Medium",
            "checker": "authentication_dispositioned",
            "finding_message": "Specify authentication disposition before implementation begins.",
        },
        {
            "name": "Authorization dispositioned",
            "applies_when": ["AUTHENTICATION", "PUBLIC_API", "PUBLIC_ENDPOINT"],
            "required_disposition": "satisfied",
            "description": "Authorization requirements are identified or explicitly not applicable.",
            "severity": "Medium",
            "checker": "authorization_dispositioned",
            "finding_message": "Specify authorization disposition before implementation begins.",
        },
        {
            "name": "Error handling dispositioned",
            "applies_when": ["REST_API", "PUBLIC_API", "PUBLIC_ENDPOINT"],
            "required_disposition": "satisfied",
            "description": "Error-handling and information-disclosure expectations are identified.",
            "severity": "Medium",
            "checker": "error_handling_dispositioned",
            "finding_message": "Specify secure error-handling expectations before implementation begins.",
        },
    ],
    "Tester": [
        {
            "name": "Acceptance criteria exist",
            "applies_when": [],
            "required_disposition": "satisfied",
            "description": "Every requirement contains acceptance criteria.",
            "severity": "High",
            "checker": "acceptance_criteria_exist",
            "finding_message": "Add acceptance criteria to every requirement.",
        },
        {
            "name": "Negative paths identified",
            "applies_when": [],
            "required_disposition": "satisfied",
            "description": "Negative, invalid, rejected, or failure-path behavior is identified.",
            "severity": "Medium",
            "checker": "negative_paths_identified",
            "finding_message": "Identify negative-path validation before implementation begins.",
        },
    ],
    "Developer": [
        {
            "name": "Implementation technology identified",
            "applies_when": [],
            "required_disposition": "satisfied",
            "description": "The implementation language, runtime, framework, or executable technology is identified.",
            "severity": "High",
            "checker": "technology_stack_identified",
            "finding_message": "Identify implementation technology before coding begins.",
        },
    ],
    "DevOps": [
        {
            "name": "Deployment environment identified",
            "applies_when": [],
            "required_disposition": "satisfied",
            "description": "Deployment, hosting, container, or local execution environment is identified.",
            "severity": "Medium",
            "checker": "deployment_environment_identified",
            "finding_message": "Identify the deployment or execution environment before implementation begins.",
        },
    ],
    "SRE": [
        {
            "name": "Operational readiness considered",
            "applies_when": ["REST_API", "DOCKER", "BACKGROUND_PROCESS", "PUBLIC_ENDPOINT"],
            "required_disposition": "satisfied",
            "description": "Operational execution, startup, reliability, or readiness concerns are represented.",
            "severity": "Medium",
            "checker": "operational_readiness_considered",
            "finding_message": "Consider operational readiness before implementation begins.",
        },
    ],
    "UX": [
        {
            "name": "User interaction identified when applicable",
            "applies_when": ["USER_INTERFACE", "CLI"],
            "required_disposition": "satisfied",
            "description": "User-facing interaction expectations are identified.",
            "severity": "Medium",
            "checker": "user_interaction_identified",
            "finding_message": "Identify user interaction expectations before implementation begins.",
        },
    ],
}


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values())
    return ""


def _contains(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _constraints(ledger: Dict[str, Any], category: str = "") -> List[Dict[str, Any]]:
    values = ledger.get("constraints", {})
    if not isinstance(values, dict):
        return []
    if category:
        entries = values.get(category, [])
        return entries if isinstance(entries, list) else []
    return [entry for entries in values.values() if isinstance(entries, list) for entry in entries if isinstance(entry, dict)]


def infer_attributes(mission: Dict[str, Any], ledger: Dict[str, Any]) -> List[str]:
    prompt = _text(mission.get("mission_prompt") or mission.get("original_prompt") or ledger.get("mission_prompt"))
    contract_text = " ".join([prompt, _text(ledger.get("requirements", [])), _text(ledger.get("constraints", {}))])
    attributes = set()
    if _contains(contract_text, r"\brest\b|\bapi\b"):
        attributes.add("REST_API")
    if _contains(contract_text, r"\bdocker\b|\bcontainer"):
        attributes.add("DOCKER")
    if _contains(contract_text, r"\bauth(?:entication|orization)?\b|\bjwt\b|\blogin\b|\btoken\b|\bidentity\b"):
        attributes.add("AUTHENTICATION")
    if _contains(contract_text, r"\bdatabase\b|\bpostgres\b|\bmysql\b|\bsqlite\b|\bredis\b"):
        attributes.add("DATABASE")
    if _contains(contract_text, r"\bui\b|\buser interface\b|\bfrontend\b|\bweb app\b|\bscreen\b"):
        attributes.add("USER_INTERFACE")
    if _contains(contract_text, r"\bcli\b|\bcommand[- ]line\b"):
        attributes.add("CLI")
    if _contains(contract_text, r"\bworker\b|\bbackground\b|\bdaemon\b|\bqueue\b"):
        attributes.add("BACKGROUND_PROCESS")
    if _contains(contract_text, r"\bpublic api\b"):
        attributes.add("PUBLIC_API")
    if _contains(contract_text, r"\bpublic endpoint\b"):
        attributes.add("PUBLIC_ENDPOINT")
    return sorted(attributes)


def _open_clarifications(ledger: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        item for item in ledger.get("clarifications", [])
        if isinstance(item, dict) and item.get("status") == "open"
    ]


def _requirements(ledger: Dict[str, Any]) -> List[Dict[str, Any]]:
    values = ledger.get("requirements", [])
    return values if isinstance(values, list) else []


def _has_requirement_text(ledger: Dict[str, Any], pattern: str) -> bool:
    return _contains(_text(_requirements(ledger)), pattern)


def _has_constraint_text(ledger: Dict[str, Any], pattern: str) -> bool:
    return _contains(_text(_constraints(ledger)), pattern)


def _resolved_answer(ledger: Dict[str, Any], pattern: str) -> bool:
    return any(
        isinstance(item, dict)
        and item.get("status") in {"resolved", "superseded", "rejected"}
        and (_contains(_text(item.get("question")), pattern) or _contains(_text(item.get("answer")), pattern))
        for item in ledger.get("clarifications", [])
    )


def _checker_result(checker: str, mission: Dict[str, Any], ledger: Dict[str, Any], attributes: List[str]) -> bool:
    prompt = _text(mission.get("mission_prompt") or mission.get("original_prompt") or ledger.get("mission_prompt"))
    if checker == "clarifications_resolved":
        return not _open_clarifications(ledger)
    if checker == "risks_documented":
        return bool(ledger.get("risks"))
    if checker == "assumptions_documented":
        return bool(ledger.get("assumptions"))
    if checker == "acceptance_criteria_exist":
        requirements = _requirements(ledger)
        return bool(requirements) and all(isinstance(item, dict) and item.get("acceptance") for item in requirements)
    if checker == "negative_paths_identified":
        return _has_requirement_text(ledger, r"negative|invalid|unsupported|reject|failure|malicious|malformed")
    if checker == "technology_stack_identified":
        return bool(_constraints(ledger, "technical")) or _resolved_answer(ledger, r"framework|typescript|node|python|fastify|express|django|flask")
    if checker == "application_boundary_identified":
        return _has_requirement_text(ledger, r"entrypoint|application|service|endpoint|cli|interface")
    if checker == "api_contract_identified":
        if "REST_API" not in attributes and "PUBLIC_API" not in attributes and "PUBLIC_ENDPOINT" not in attributes:
            return True
        return bool(_constraints(ledger, "functional")) and not any("endpoint path" in _text(item.get("question")).lower() for item in _open_clarifications(ledger))
    if checker == "authentication_dispositioned":
        if "AUTHENTICATION" in attributes:
            return _has_constraint_text(ledger, r"auth|jwt|token|identity") or _has_requirement_text(ledger, r"auth|jwt|token|identity")
        return "PUBLIC_API" not in attributes and "PUBLIC_ENDPOINT" not in attributes
    if checker == "authorization_dispositioned":
        if "AUTHENTICATION" in attributes:
            return _has_requirement_text(ledger, r"permission|authorization|authorize|access|reject|auth|jwt|token")
        return "PUBLIC_API" not in attributes and "PUBLIC_ENDPOINT" not in attributes
    if checker == "error_handling_dispositioned":
        if not any(attribute in attributes for attribute in ("REST_API", "PUBLIC_API", "PUBLIC_ENDPOINT")):
            return True
        return _has_constraint_text(ledger, r"owasp|error|malformed|disclos") or _has_requirement_text(ledger, r"error|malformed|stack traces|disclos|unsupported")
    if checker == "deployment_environment_identified":
        return bool(_constraints(ledger, "operational")) or _contains(prompt, r"\bdocker\b|\blocal\b|\baws\b|\bazure\b|\bgcp\b|\bkubernetes\b|\bserverless\b|\bhosting\b|\bcontainer")
    if checker == "operational_readiness_considered":
        return bool(_constraints(ledger, "operational")) or _has_requirement_text(ledger, r"documentation|startup|run|operat|container|local")
    if checker == "user_interaction_identified":
        return _has_requirement_text(ledger, r"user|interface|screen|flow|cli|command")
    return False


def evaluate_obligations(mission: Dict[str, Any], ledger: Dict[str, Any], attributes: List[str]) -> List[Dict[str, Any]]:
    findings = []
    attribute_set = set(attributes)
    for discipline, obligations in OBLIGATION_PACKS.items():
        for obligation in obligations:
            applies_when = obligation.get("applies_when", [])
            applies = not applies_when or bool(attribute_set.intersection(applies_when))
            status = "NOT_APPLICABLE"
            if applies:
                status = "SATISFIED" if _checker_result(obligation["checker"], mission, ledger, attributes) else "NEEDS_CLARIFICATION"
            findings.append({
                "discipline": discipline,
                "obligation": obligation["name"],
                "status": status,
                "severity": obligation["severity"],
                "recommendation": "No action required." if status in {"SATISFIED", "NOT_APPLICABLE"} else obligation["finding_message"],
                "description": obligation["description"],
                "applies_when": list(applies_when),
                "required_disposition": obligation["required_disposition"],
            })
    return findings


def _readiness(ledger: Dict[str, Any], findings: List[Dict[str, Any]]) -> str:
    requirements = _requirements(ledger)
    if _open_clarifications(ledger):
        return "NOT_READY"
    if not requirements:
        return "NOT_READY"
    if any(not isinstance(requirement, dict) or not requirement.get("acceptance") for requirement in requirements):
        return "NOT_READY"
    unsatisfied = [item for item in findings if item["status"] == "NEEDS_CLARIFICATION"]
    if unsatisfied:
        return "PARTIALLY_READY"
    if ledger.get("assumptions") or ledger.get("risks"):
        return "READY_WITH_RISK"
    return "READY"


def _recommendation(ledger: Dict[str, Any], findings: List[Dict[str, Any]], readiness: str) -> str:
    requirements = _requirements(ledger)
    if _open_clarifications(ledger):
        return "Resolve Clarifications"
    if not requirements or any(not isinstance(requirement, dict) or not requirement.get("acceptance") for requirement in requirements):
        return "Refine Requirements"
    if any(item["discipline"] == "Architect" and item["status"] == "NEEDS_CLARIFICATION" for item in findings):
        return "Perform Architecture Review"
    if any(item["discipline"] == "SecOps" and item["status"] == "NEEDS_CLARIFICATION" for item in findings):
        return "Perform Security Review"
    if readiness in {"READY", "READY_WITH_RISK"}:
        return "Proceed to Implementation"
    return "Complete Mission Planning"


def _mission_summary(mission: Dict[str, Any], ledger: Dict[str, Any]) -> str:
    prompt = mission.get("mission_prompt") or mission.get("original_prompt") or ledger.get("mission_prompt") or ""
    requirements = len(_requirements(ledger))
    clarifications = len(ledger.get("clarifications", []) if isinstance(ledger.get("clarifications"), list) else [])
    return f"{prompt} Requirements: {requirements}. Clarifications: {clarifications}."


def assess(workspace: Path) -> Dict[str, Any]:
    mission = read_yaml(workspace / "mission.yaml")
    ledger = read_yaml(workspace / "ledger.yaml")
    attributes = infer_attributes(mission, ledger)
    findings = evaluate_obligations(mission, ledger, attributes)
    readiness = _readiness(ledger, findings)
    recommendation = _recommendation(ledger, findings, readiness)
    open_clarifications = _open_clarifications(ledger)
    obligations_total = len(findings)
    obligations_satisfied = len([item for item in findings if item["status"] == "SATISFIED"])
    obligations_not_applicable = len([item for item in findings if item["status"] == "NOT_APPLICABLE"])
    obligations_needing_action = len([item for item in findings if item["status"] == "NEEDS_CLARIFICATION"])
    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp": mission.get("created_at") or "UNKNOWN",
        "mission": {
            "id": mission.get("id"),
            "title": mission.get("title"),
            "objective": mission.get("objective"),
            "prompt": mission.get("mission_prompt") or mission.get("original_prompt"),
        },
        "mission_summary": _mission_summary(mission, ledger),
        "readiness": readiness,
        "recommendation": recommendation,
        "next_engineering_activity": recommendation,
        "mission_attributes": attributes,
        "outstanding_clarifications": [
            {"id": item.get("id"), "question": item.get("question"), "status": item.get("status")}
            for item in open_clarifications
        ],
        "assumptions": ledger.get("assumptions", []) if isinstance(ledger.get("assumptions"), list) else [],
        "risks": ledger.get("risks", []) if isinstance(ledger.get("risks"), list) else [],
        "engineering_obligation_summary": {
            "total": obligations_total,
            "satisfied": obligations_satisfied,
            "not_applicable": obligations_not_applicable,
            "needs_action": obligations_needing_action,
        },
        "discipline_findings": findings,
        "rules": [
            "Open clarifications produce NOT_READY.",
            "Missing requirements produce NOT_READY.",
            "Missing acceptance criteria produce NOT_READY.",
            "Unsatisfied applicable obligations produce PARTIALLY_READY.",
            "Satisfied obligations with assumptions or risks produce READY_WITH_RISK.",
            "Satisfied obligations without assumptions or risks produce READY.",
        ],
    }


def render_assessment_markdown(assessment: Dict[str, Any]) -> str:
    bullet = lambda values: "\n".join("- " + str(value) for value in values) if values else "- None"
    clarifications = [
        f"{item.get('id', '—')}: {item.get('question', '—')} [{item.get('status', '—')}]"
        for item in assessment.get("outstanding_clarifications", [])
    ]
    assumptions = [
        f"{item.get('id', '—')}: {item.get('statement', item)}" if isinstance(item, dict) else str(item)
        for item in assessment.get("assumptions", [])
    ]
    risks = [
        f"{item.get('id', '—')}: {item.get('statement', item)}" if isinstance(item, dict) else str(item)
        for item in assessment.get("risks", [])
    ]
    findings = [
        (
            f"{item['discipline']} — {item['obligation']} — {item['status']} "
            f"({item['severity']}): {item['recommendation']}"
        )
        for item in assessment.get("discipline_findings", [])
    ]
    summary = assessment.get("engineering_obligation_summary", {})
    mission = assessment.get("mission", {})
    return f"""# Battalion Mission Assessment

## Mission

- **ID:** {mission.get('id', '—')}
- **Title:** {mission.get('title', '—')}
- **Objective:** {mission.get('objective', '—')}
- **Prompt:** {mission.get('prompt', '—')}

## Assessment Summary

{assessment.get('mission_summary', '—')}

## Readiness

- **Readiness:** {assessment.get('readiness', '—')}
- **Recommendation:** {assessment.get('recommendation', '—')}

## Mission Attributes

{bullet(assessment.get('mission_attributes', []))}

## Outstanding Clarifications

{bullet(clarifications)}

## Assumptions

{bullet(assumptions)}

## Risks

{bullet(risks)}

## Engineering Obligation Summary

- **Total:** {summary.get('total', 0)}
- **Satisfied:** {summary.get('satisfied', 0)}
- **Needs action:** {summary.get('needs_action', 0)}
- **Not applicable:** {summary.get('not_applicable', 0)}

## Discipline Findings

{bullet(findings)}

## Recommendation

{assessment.get('recommendation', '—')}

## Next Engineering Activity

{assessment.get('next_engineering_activity', '—')}

## Timestamp

{assessment.get('timestamp', '—')}

## Schema Version

{assessment.get('schema_version', '—')}
"""


def write_assessment(workspace: Path) -> Dict[str, Any]:
    result = assess(workspace)
    (workspace / "assessment.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (workspace / "assessment.md").write_text(render_assessment_markdown(result), encoding="utf-8")
    return result
