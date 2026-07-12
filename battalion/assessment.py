"""Deterministic mission assessment and engineering readiness evaluation."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .classification import AttributeCatalogLoader, MissionClassifier, default_attribute_catalog
from .storage import read_yaml, timestamp, write_yaml


SCHEMA_VERSION = "battalion.assessment.v2"
ENGINEERING_COMPATIBILITY_DISCLAIMER = (
    "Framework, SDK, runtime, library, package, platform, and standards versions must always be validated by the human engineering team for compatibility during implementation, testing, and assurance."
)
READINESS_LEVELS = ("NOT_READY", "PARTIALLY_READY", "READY_WITH_RISK", "READY")
ASSESSMENT_OUTCOMES = ("UNDERSTOOD", "PROCEED_WITH_ASSUMPTIONS", "CLARIFICATION_REQUIRED")
MISSION_DOMAINS = ("api", "data", "ui", "infra", "security", "documentation", "testing", "unknown")
MISSION_SCALES = ("task", "slice", "user_story", "feature", "epic", "unknown")
PLAYBOOKS_PATH = Path(__file__).with_name("playbooks.yml")
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
            "applies_when": ["REST_API", "PUBLIC_API", "PUBLIC_ENDPOINT", "HTTP_ENDPOINT"],
            "required_disposition": "satisfied",
            "description": "API behavior, endpoint, or contract information is identified.",
            "severity": "High",
            "checker": "api_contract_identified",
            "finding_message": "Define the API contract before implementation begins.",
        },
        {
            "name": "HTTP endpoint contract identified",
            "applies_when": ["HTTP_ENDPOINT", "REST_API", "PUBLIC_ENDPOINT"],
            "required_disposition": "satisfied",
            "description": "HTTP endpoint path and method expectations are identified.",
            "severity": "High",
            "checker": "http_endpoint_contract_identified",
            "finding_message": "Define endpoint path and HTTP method expectations before implementation begins.",
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
        {
            "name": "HTTP method enforcement identified",
            "applies_when": ["GET_ONLY"],
            "required_disposition": "satisfied",
            "description": "HTTP method restrictions and rejection behavior are identified.",
            "severity": "Medium",
            "checker": "http_method_enforcement_identified",
            "finding_message": "Identify HTTP method enforcement and rejection behavior before implementation begins.",
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
        {
            "name": "Happy-path tests identified",
            "applies_when": ["TESTING_REQUIRED"],
            "required_disposition": "satisfied",
            "description": "Happy-path test obligations are identified.",
            "severity": "Medium",
            "checker": "happy_path_tests_identified",
            "finding_message": "Identify happy-path tests before implementation begins.",
        },
        {
            "name": "Negative-path tests identified",
            "applies_when": ["TESTING_REQUIRED"],
            "required_disposition": "satisfied",
            "description": "Negative-path test obligations are identified.",
            "severity": "Medium",
            "checker": "negative_paths_identified",
            "finding_message": "Identify negative-path tests before implementation begins.",
        },
        {
            "name": "Malicious-request tests identified",
            "applies_when": ["MALICIOUS_TESTING"],
            "required_disposition": "satisfied",
            "description": "Malicious-request test obligations are identified.",
            "severity": "Medium",
            "checker": "malicious_request_tests_identified",
            "finding_message": "Identify malicious-request tests before implementation begins.",
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
        {
            "name": "Runtime selection confirmed",
            "applies_when": ["NODE", "TYPESCRIPT", "REST_API", "CLI", "BACKGROUND_PROCESS"],
            "required_disposition": "satisfied",
            "description": "The runtime or execution environment for implementation is identified.",
            "severity": "High",
            "checker": "runtime_selection_confirmed",
            "finding_message": "Confirm runtime selection before implementation begins.",
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


def load_mission_playbooks(path: Path = None) -> Dict[str, Any]:
    target = path or PLAYBOOKS_PATH
    try:
        data = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot read {target.name}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("playbooks"), dict):
        raise ValueError("playbooks.yml must contain a playbooks mapping.")
    return data


def classify_requirement_playbook(requirement: str, catalog: Dict[str, Any] = None) -> Dict[str, Any]:
    catalog = catalog or load_mission_playbooks()
    playbooks = catalog.get("playbooks", {})
    text = requirement.lower()
    matches = []
    for key in sorted(playbooks):
        playbook = playbooks[key]
        keywords = playbook.get("keywords", []) if isinstance(playbook, dict) else []
        matched = []
        for keyword in keywords:
            if _keyword_matches(text, str(keyword)):
                matched.append(str(keyword))
        if matched:
            matches.append({
                "key": key,
                "hit_count": len(matched),
                "matched_keywords": matched,
                "playbook": playbook,
            })
    if not matches:
        return {
            "status": "unclassified",
            "key": "unknown.unknown",
            "parent": "unknown",
            "subtype": "unknown",
            "display": "Unknown / Unknown",
            "description": "Unknown mission work",
            "hit_count": 0,
            "matched_keywords": [],
            "tie_candidates": [],
            "playbook": {},
        }
    matches.sort(key=lambda item: (-item["hit_count"], item["key"]))
    strongest = matches[0]["hit_count"]
    strongest_matches = [item for item in matches if item["hit_count"] == strongest]
    if len(strongest_matches) > 1:
        return {
            "status": "tie",
            "key": "ambiguous.ambiguous",
            "parent": "ambiguous",
            "subtype": "ambiguous",
            "display": "Ambiguous Mission Type",
            "description": "Multiple mission playbooks matched equally.",
            "hit_count": strongest,
            "matched_keywords": sorted({keyword for item in strongest_matches for keyword in item["matched_keywords"]}),
            "tie_candidates": [item["key"] for item in strongest_matches],
            "playbook": {},
        }
    selected = matches[0]
    parent, subtype = selected["key"].split(".", 1)
    playbook = selected["playbook"]
    return {
        "status": "classified",
        "key": selected["key"],
        "parent": parent,
        "subtype": subtype,
        "display": f"{_title_label(parent)} / {_title_label(subtype)}",
        "description": playbook.get("description", selected["key"]),
        "hit_count": selected["hit_count"],
        "matched_keywords": selected["matched_keywords"],
        "tie_candidates": [],
        "playbook": playbook,
    }


def _keyword_matches(text: str, keyword: str) -> bool:
    lowered = keyword.lower()
    if re.search(r"[^a-z0-9_ ]", lowered):
        return lowered in text
    return re.search(rf"\b{re.escape(lowered)}\b", text, flags=re.IGNORECASE) is not None


def _title_label(value: str) -> str:
    labels = {
        "api": "API",
        "ui": "UI",
        "adr": "ADR",
        "readme": "README",
        "open_knowledge": "Open Knowledge",
        "infrastructure": "Infrastructure",
        "deployment": "Deployment",
        "endpoint": "Endpoint",
        "data": "Data",
        "model": "Model",
        "documentation": "Documentation",
        "testing": "Testing",
        "automated": "Automated",
    }
    return labels.get(value, value.replace("_", " ").title())


def assess_requirement_text(requirement: str) -> Dict[str, Any]:
    """Produce the concise v1 requirement-understanding model.

    This deliberately answers a narrower question than full Mission Assurance:
    does Battalion understand this requirement well enough to proceed to planning?
    The model is deterministic and asks only material implementation or
    verification questions.
    """
    text = requirement.strip()
    playbook_match = classify_requirement_playbook(text)
    domains = _detect_requirement_domains(text)
    if playbook_match["parent"] == "infrastructure":
        domains = ["infra"] + [domain for domain in domains if domain != "infra"]
    elif playbook_match["parent"] not in {"unknown", "ambiguous"}:
        mapped_parent = "infra" if playbook_match["parent"] == "infrastructure" else playbook_match["parent"]
        domains = [mapped_parent] + [domain for domain in domains if domain != mapped_parent]
    scale = _detect_requirement_scale(text, domains)
    understanding = _requirement_understanding(text, domains, playbook_match)
    assumptions = _requirement_assumptions(text, domains, playbook_match)
    question_details = _playbook_question_details(text, playbook_match)
    questions = [_question_text(item) for item in question_details] + _material_questions(text, domains)
    questions = _dedupe(questions)
    out_of_scope = _playbook_out_of_scope(playbook_match) or _out_of_scope_domains(domains)

    if playbook_match["status"] == "tie":
        outcome = "CLARIFICATION_REQUIRED"
        confidence = "medium"
        questions = [f"Which mission type applies: {', '.join(playbook_match['tie_candidates'])}?"]
        question_details = [{
            "id": "mission.type",
            "question": questions[0],
            "examples": playbook_match["tie_candidates"],
        }]
        recommendation = "Answer mission questions before planning."
    elif questions:
        outcome = "CLARIFICATION_REQUIRED"
        confidence = "high" if playbook_match["status"] == "classified" else ("medium" if domains != ["unknown"] else "low")
        recommendation = "Answer mission questions before planning."
    elif assumptions:
        outcome = "PROCEED_WITH_ASSUMPTIONS"
        confidence = "high" if domains != ["unknown"] else "medium"
        recommendation = "Proceed to planning."
    else:
        outcome = "UNDERSTOOD"
        confidence = "high" if domains != ["unknown"] else "medium"
        recommendation = "Proceed to planning."

    if not text:
        outcome = "CLARIFICATION_REQUIRED"
        confidence = "low"
        understanding = []
        questions = ["What requirement should Battalion assess?"]
        recommendation = "Provide a requirement before planning."

    return {
        "outcome": outcome,
        "confidence": confidence,
        "mission_type": {
            "key": playbook_match["key"],
            "parent": playbook_match["parent"],
            "subtype": playbook_match["subtype"],
            "display": playbook_match["display"],
            "description": playbook_match["description"],
            "hit_count": playbook_match["hit_count"],
            "matched_keywords": playbook_match["matched_keywords"],
            "tie_candidates": playbook_match["tie_candidates"],
        },
        "mission_intent": _mission_intent(text, playbook_match),
        "understanding": understanding,
        "detected_scale": scale,
        "detected_domains": domains,
        "assumptions": assumptions,
        "blocking_ambiguities": questions,
        "questions": questions,
        "question_details": question_details,
        "out_of_scope": out_of_scope,
        "recommendation": recommendation,
    }


def _detect_requirement_domains(text: str) -> List[str]:
    checks = [
        ("api", r"\b(endpoint|api|route|get|post|put|patch|delete|http|rest)\b"),
        ("data", r"\b(database|schema|migration|column|entity|model|table|sql)\b"),
        ("ui", r"\b(screen|page|form|button|ux|ui|modal|frontend|react|view)\b"),
        ("infra", r"\b(deploy|deployment|docker|container|kubernetes|terraform|pipeline|infrastructure|hosting|azure app service|app service)\b"),
        ("security", r"\b(auth|jwt|oauth|permission|security|encrypt|secret|owasp|authorization|authentication)\b"),
        ("documentation", r"\b(documentation|readme|markdown|docs?|installation instructions)\b"),
        ("testing", r"\b(test|tests|testing|spec|validation|happy-path|negative-path|malicious)\b"),
    ]
    domains = [domain for domain, pattern in checks if _contains(text, pattern)]
    return domains or ["unknown"]


def _detect_requirement_scale(text: str, domains: List[str]) -> str:
    if _contains(text, r"\b(epic|program|platform|multi[- ]team|roadmap)\b"):
        return "epic"
    if _contains(text, r"\b(feature|capability|module)\b"):
        return "feature"
    if _contains(text, r"\bas a\b.+\bi want\b|\buser story\b"):
        return "user_story"
    if _contains(text, r"\b(endpoint|column|readme|button|modal|migration|bug|fix|update|add|create)\b"):
        return "slice" if len(domains) > 1 and "unknown" not in domains else "task"
    return "unknown"


def _requirement_understanding(text: str, domains: List[str], playbook_match: Dict[str, Any] = None) -> List[str]:
    playbook_match = playbook_match or {}
    values = []
    if playbook_match.get("status") == "classified":
        values.append(_mission_intent(text, playbook_match))
    if "api" in domains:
        values.append("Backend API enhancement")
        if _contains(text, r"\bretrieve|read|get\b") and not _contains(text, r"\bpost|put|patch|delete|create|update|remove\b"):
            values.append("Read-only endpoint")
    if "data" in domains:
        values.append("Data/schema change")
    if "ui" in domains:
        values.append("User interface change")
    if "documentation" in domains:
        if _contains(text, r"\breadme(?:\.md)?\b") and _contains(text, r"\bcreate\b"):
            values.append("Create a README documentation artifact.")
        else:
            values.append("Documentation update")
    if "infra" in domains:
        values.append("Infrastructure or deployment change")
    if "testing" in domains:
        values.append("Testing or validation work")
    if "security" in domains:
        values.append("Security-sensitive behavior")
    if "ui" not in domains:
        values.append("No UI detected")
    return _dedupe(values) or ["Requirement type is not yet classified"]


def _requirement_assumptions(text: str, domains: List[str], playbook_match: Dict[str, Any] = None) -> List[str]:
    playbook_match = playbook_match or {}
    assumptions = []
    playbook = playbook_match.get("playbook", {}) if isinstance(playbook_match.get("playbook"), dict) else {}
    assumptions.extend(playbook.get("defaultAssumptions", []) if isinstance(playbook.get("defaultAssumptions"), list) else [])
    if "api" in domains:
        assumptions.append("Existing API conventions apply.")
        if _contains(text, r"\bcustomer|user|account|order|email\b"):
            assumptions.append("Existing data model contains the referenced field or entity.")
        if not _contains(text, r"\bpublic|anonymous|unauthenticated|no auth\b") and not any("authentication middleware applies" in item for item in assumptions):
            assumptions.append("Existing authentication middleware applies.")
    if "data" in domains:
        assumptions.append("Existing database migration conventions apply.")
    if "ui" in domains:
        assumptions.append("Existing design system and UI conventions apply.")
    return _dedupe(assumptions)


def _playbook_question_details(text: str, playbook_match: Dict[str, Any]) -> List[Dict[str, Any]]:
    playbook = playbook_match.get("playbook", {}) if isinstance(playbook_match.get("playbook"), dict) else {}
    questions = []
    for item in playbook.get("leadingQuestions", []) if isinstance(playbook.get("leadingQuestions"), list) else []:
        question_id = item.get("id")
        if _playbook_question_answered(text, playbook_match, question_id):
            continue
        question = item.get("question")
        if not question:
            continue
        examples = item.get("examples", [])
        questions.append({
            "id": f"{_question_id_prefix(playbook_match)}.{question_id}",
            "question": question,
            "examples": [str(example) for example in examples] if isinstance(examples, list) else [],
        })
    return questions


def _question_id_prefix(playbook_match: Dict[str, Any]) -> str:
    if playbook_match.get("parent") == "api":
        return "api"
    return playbook_match.get("subtype") or playbook_match.get("parent") or "mission"


def _question_text(item: Dict[str, Any]) -> str:
    examples = item.get("examples", [])
    if examples:
        return f"{item.get('question')} Examples: {', '.join(str(example) for example in examples)}."
    return item.get("question", "")


def _playbook_question_answered(text: str, playbook_match: Dict[str, Any], question_id: str) -> bool:
    key = playbook_match.get("key")
    if key == "documentation.readme":
        if _contains(text, r"\bblank\b|\binitiali[sz]e\b|\boverview\b|\binstall(?:ation)?\b|\busage\b"):
            return True
        if question_id == "audience" and _contains(text, r"\binternal|external|developer|user|operator|public\b"):
            return True
        return False
    if key == "api.endpoint":
        if question_id == "purpose":
            return _contains(text, r"\bretrieve|return|get|add|update|delete|health|email\b") or _contains(text, r"/[a-z0-9_/{}/.-]+")
        if question_id == "data_flow":
            return (
                _contains(text, r"\bGET|POST|PUT|PATCH|DELETE\b") and _contains(text, r"/[a-z0-9_/{}/.-]+")
            ) or _contains(text, r"\bretrieve|return|get\b") and _contains(text, r"\bemail|status|health|json|response\b")
        if question_id == "operations":
            return (
                _contains(text, r"\bGET|POST|PUT|PATCH|DELETE\b") and _contains(text, r"/[a-z0-9_/{}/.-]+")
            ) or _contains(text, r"\bendpoint\b") and _contains(text, r"\bhealth|customer|email|retrieve|return\b")
        if question_id == "security":
            return _contains(text, r"/[a-z0-9_/{}/.-]+") or _contains(text, r"\bretrieve|return|get|health|email\b")
        if question_id == "volume":
            return _contains(text, r"/[a-z0-9_/{}/.-]+") or _contains(text, r"\bretrieve|return|get|health|email\b")
    if key == "data.model":
        if question_id == "entity":
            return _contains(text, r"\bcustomer|user|account|order|table|entity|model\b")
        if question_id == "fields_relationships":
            return _contains(text, r"\bcolumn|field|relationship|emailaddress|email\b")
        if question_id in {"migration_backfill", "constraints_defaults"}:
            return True
    if key == "ui.component":
        if question_id == "interaction":
            return _contains(text, r"\bstyling|style|button|form|modal|page|component\b")
        if question_id in {"states", "data_dependency", "accessibility_validation"}:
            return True
    if key == "infrastructure.deployment":
        if question_id == "target_environment":
            return _contains(text, r"\bazure app service|app service|kubernetes|docker|container|environment\b")
        if question_id in {"deployment_artifact", "rollback", "configuration_secrets"}:
            return False
    if key == "testing.automated":
        if question_id == "test_type":
            return _contains(text, r"\bunit test|integration test|e2e|end[- ]to[- ]end|test suite\b")
        if question_id == "behavior_under_test":
            return _contains(text, r"\bfor|validate|verify|regression|happy|negative|failure\b")
        if question_id == "test_location":
            return _contains(text, r"\btests?/[a-z0-9_./-]+|tests?/test_[a-z0-9_./-]+|existing (?:test|regression)|regression tests?\b")
        return False
    if key == "documentation.adr":
        if question_id == "decision":
            return _contains(text, r"\badr\b|\bdecision\b")
        return False
    if key == "documentation.open_knowledge":
        if question_id == "topic":
            return _contains(text, r"\bopen knowledge|knowledge base|knowledge framework|okf\b")
        return False
    return False


def _playbook_out_of_scope(playbook_match: Dict[str, Any]) -> List[str]:
    playbook = playbook_match.get("playbook", {}) if isinstance(playbook_match.get("playbook"), dict) else {}
    values = playbook.get("outOfScope", [])
    if not isinstance(values, list):
        return []
    return ["infra" if value == "infrastructure" else value for value in values]


def _mission_intent(text: str, playbook_match: Dict[str, Any]) -> str:
    key = playbook_match.get("key")
    if key == "documentation.readme":
        if _contains(text, r"\bblank\b") and _contains(text, r"\binitiali[sz]e\b|\brepo(?:sitory)?\b"):
            return "Create a blank README.md file to initialize the repository."
        return "Create a README.md file."
    if key == "api.endpoint":
        return "Create or update the requested API endpoint."
    if key == "data.model":
        return "Create or update the requested data model change."
    if key == "ui.component":
        return "Create or update the requested UI component."
    if key == "infrastructure.deployment":
        return "Create or update the requested deployment capability."
    if key == "testing.automated":
        return "Create or update the requested automated tests."
    if key == "documentation.adr":
        return "Create or update the requested architecture decision record."
    if key == "documentation.open_knowledge":
        return "Create or update the requested open knowledge artifact."
    if playbook_match.get("status") == "tie":
        return "Clarify which mission type should govern this work."
    return text or "Mission intent is not yet understood."


def _dedupe(values: List[str]) -> List[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _material_questions(text: str, domains: List[str]) -> List[str]:
    questions = []
    if _contains(text, r"\bsearch\b"):
        if not _contains(text, r"\bexact|partial|fuzzy|full[- ]text\b"):
            questions.append("Should search be exact, partial, fuzzy, or full text?")
        if not _contains(text, r"\b(name|email|id|phone|address|field|fields)\b"):
            questions.append("Which fields should customer search include?" if _contains(text, r"\bcustomer\b") else "Which fields should search include?")
    if "unknown" in domains and _contains(text, r"\badd|create|build|implement|update\b") and len(text.split()) <= 4:
        questions.append("What behavior should be implemented or changed?")
    return questions


def _out_of_scope_domains(domains: List[str]) -> List[str]:
    values = []
    for domain in ("api", "data", "ui", "infra"):
        if domain not in domains and domains != ["unknown"]:
            values.append(domain)
    return values


def _mission_scoped_findings(findings: List[Dict[str, Any]], requirement_assessment: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Discard findings that review the broader project instead of this mission."""
    domains = set(requirement_assessment.get("detected_domains", []))
    if not domains or domains == {"unknown"}:
        return [
            finding for finding in findings
            if _finding_material_to_unknown_mission(finding)
        ]
    return [
        finding for finding in findings
        if _finding_material_to_domains(finding, domains)
    ]


def _finding_material_to_unknown_mission(finding: Dict[str, Any]) -> bool:
    if finding.get("status") == "SATISFIED":
        return True
    return finding.get("discipline") in {"Mission Analyst", "Tester"}


def _finding_material_to_domains(finding: Dict[str, Any], domains: set) -> bool:
    discipline = finding.get("discipline")
    obligation = finding.get("obligation", "")
    status = finding.get("status")

    if status == "SATISFIED":
        return True
    if obligation in {"Technology stack identified", "Implementation technology identified", "Runtime selection confirmed"}:
        return False
    if obligation == "Deployment environment identified":
        return "infra" in domains
    if obligation == "Operational readiness considered":
        return "infra" in domains
    if discipline == "SecOps":
        return bool({"api", "security"}.intersection(domains))
    if discipline == "UX":
        return "ui" in domains
    if obligation in {"API contract identified", "HTTP endpoint contract identified"}:
        return "api" in domains
    if discipline == "Architect":
        return bool({"api", "infra"}.intersection(domains))
    if discipline == "Developer":
        return False
    if discipline == "DevOps":
        return "infra" in domains
    if discipline == "SRE":
        return "infra" in domains
    return discipline in {"Mission Analyst", "Tester"}


def _constraints(ledger: Dict[str, Any], category: str = "") -> List[Dict[str, Any]]:
    values = ledger.get("constraints", {})
    if not isinstance(values, dict):
        return []
    if category:
        entries = values.get(category, [])
        return entries if isinstance(entries, list) else []
    return [entry for entries in values.values() if isinstance(entries, list) for entry in entries if isinstance(entry, dict)]


def classify_mission(mission: Dict[str, Any], ledger: Dict[str, Any], catalog: Dict[str, Any] = None) -> Dict[str, Any]:
    return MissionClassifier(catalog or default_attribute_catalog()).classify(mission, ledger)


def infer_attribute_sources(mission: Dict[str, Any], ledger: Dict[str, Any]) -> Dict[str, List[str]]:
    classification = classify_mission(mission, ledger)
    return _attribute_sources_from_classification(classification)


def infer_attributes(mission: Dict[str, Any], ledger: Dict[str, Any]) -> List[str]:
    return sorted(classify_mission(mission, ledger)["detected_attributes"])


def _attribute_sources_from_classification(classification: Dict[str, Any]) -> Dict[str, List[str]]:
    sources = {}
    for item in classification.get("attributes", []):
        if not item.get("classified"):
            continue
        matched = [entry.get("indicator", "") for entry in item.get("classification_evidence", [])]
        sources[item["attribute"]] = [
            "Matched indicator(s): " + ", ".join(matched) if matched else "Matched configured threshold."
        ]
    return {key: sources[key] for key in sorted(sources)}


def _attribute_catalog(workspace: Path) -> Dict[str, Any]:
    path = workspace / "attributes.yml"
    legacy_path = workspace / "attributes.yaml"
    if not path.is_file() and legacy_path.is_file():
        path = legacy_path
    if not path.is_file():
        return default_attribute_catalog()
    return AttributeCatalogLoader(path).load()


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


def _all_clarifications_terminal(ledger: Dict[str, Any]) -> bool:
    clarifications = ledger.get("clarifications", [])
    return isinstance(clarifications, list) and all(
        isinstance(item, dict) and item.get("status") in {"resolved", "superseded", "rejected"}
        for item in clarifications
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
    if checker == "happy_path_tests_identified":
        return _has_requirement_text(ledger, r"happy[- ]path|successful|valid request|primary mission behavior")
    if checker == "malicious_request_tests_identified":
        return _has_requirement_text(ledger, r"malicious[- ]request|malicious request|abuse|information disclosure")
    if checker == "technology_stack_identified":
        return bool(_constraints(ledger, "technical")) or _resolved_answer(ledger, r"framework|typescript|node|python|fastify|express|django|flask")
    if checker == "runtime_selection_confirmed":
        return bool(_constraints(ledger, "technical")) or _resolved_answer(ledger, r"framework|runtime|node|python|fastify|express|django|flask")
    if checker == "application_boundary_identified":
        return _has_requirement_text(ledger, r"entrypoint|application|service|endpoint|cli|interface")
    if checker == "api_contract_identified":
        if "REST_API" not in attributes and "PUBLIC_API" not in attributes and "PUBLIC_ENDPOINT" not in attributes:
            return True
        return bool(_constraints(ledger, "functional")) and not any("endpoint path" in _text(item.get("question")).lower() for item in _open_clarifications(ledger))
    if checker == "http_endpoint_contract_identified":
        if not any(attribute in attributes for attribute in ("HTTP_ENDPOINT", "REST_API", "PUBLIC_ENDPOINT")):
            return True
        return _has_requirement_text(ledger, r"endpoint|GET /|HTTP 200|request") and not any("endpoint path" in _text(item.get("question")).lower() for item in _open_clarifications(ledger))
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
    if checker == "http_method_enforcement_identified":
        return _has_constraint_text(ledger, r"Only GET|GET requests") or _has_requirement_text(ledger, r"GET requests|POST requests are rejected|PUT requests are rejected|DELETE")
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
            if not applies:
                continue
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
                "category": _finding_category(discipline, obligation["name"]),
            })
    return findings


def _finding_category(discipline: str, obligation: str) -> str:
    if discipline == "SecOps":
        return "Security"
    if discipline == "Architect":
        return "Architecture"
    if discipline in {"DevOps", "SRE"}:
        return "Operational"
    if discipline == "Developer":
        return "Implementation"
    if discipline == "Tester":
        return "Testing"
    if discipline == "UX":
        return "User Experience"
    return "Planning"


def _risk_category(risk: Dict[str, Any]) -> str:
    text = _text(risk.get("statement", risk))
    if _contains(text, r"security|owasp|auth|permission|secret|malicious|disclosure"):
        return "Security"
    if _contains(text, r"framework|architecture|endpoint|api contract|boundary"):
        return "Architecture"
    if _contains(text, r"deployment|environment|docker|container|production|runtime|operational"):
        return "Operational"
    if _contains(text, r"document|readme|instruction"):
        return "Documentation"
    return "Implementation"


def _risk_resolution_reason(risk: Dict[str, Any], ledger: Dict[str, Any]) -> str:
    text = _text(risk.get("statement", risk))
    if _contains(text, r"framework") and _resolved_answer(ledger, r"framework"):
        return "Framework clarification has been resolved."
    if _contains(text, r"owasp") and _resolved_answer(ledger, r"owasp"):
        return "OWASP baseline clarification has been resolved."
    if _contains(text, r"endpoint path") and _resolved_answer(ledger, r"endpoint path"):
        return "Endpoint path clarification has been resolved."
    return ""


def _categorized_risks(ledger: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    open_risks, resolved_risks = [], []
    for risk in ledger.get("risks", []) if isinstance(ledger.get("risks"), list) else []:
        if not isinstance(risk, dict):
            continue
        enriched = dict(risk)
        enriched["category"] = _risk_category(risk)
        reason = _risk_resolution_reason(risk, ledger)
        if reason:
            enriched["status"] = "RESOLVED"
            enriched["resolution_reason"] = reason
            resolved_risks.append(enriched)
        else:
            enriched["status"] = risk.get("status", "OPEN")
            open_risks.append(enriched)
    return {"open": open_risks, "resolved": resolved_risks}


def _resolved_assumptions(ledger: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = []
    for assumption in ledger.get("assumptions", []) if isinstance(ledger.get("assumptions"), list) else []:
        if isinstance(assumption, dict) and assumption.get("traceability", {}).get("clarification_ids"):
            item = dict(assumption)
            item["status"] = "RESOLVED"
            result.append(item)
    return result


def _readiness(ledger: Dict[str, Any], findings: List[Dict[str, Any]], open_risks: List[Dict[str, Any]]) -> str:
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
    if ledger.get("assumptions") or open_risks:
        return "READY_WITH_RISK"
    return "READY"


def _readiness_reasons(ledger: Dict[str, Any], findings: List[Dict[str, Any]], readiness: str, open_risks: List[Dict[str, Any]]) -> List[str]:
    requirements = _requirements(ledger)
    reasons = []
    if requirements:
        reasons.append(f"{len(requirements)} requirement(s) are present.")
    else:
        reasons.append("No requirements exist.")
    if _open_clarifications(ledger):
        reasons.append(f"{len(_open_clarifications(ledger))} clarification(s) remain open.")
    else:
        reasons.append("Clarifications are resolved or otherwise dispositioned.")
    if requirements and all(isinstance(requirement, dict) and requirement.get("acceptance") for requirement in requirements):
        reasons.append("Requirements include acceptance criteria.")
    else:
        reasons.append("One or more requirements lack acceptance criteria.")
    unsatisfied = [item for item in findings if item["status"] == "NEEDS_CLARIFICATION"]
    if unsatisfied:
        categories = sorted(set(item["category"] for item in unsatisfied))
        reasons.append(f"{len(unsatisfied)} applicable obligation(s) need clarification across {', '.join(categories)}.")
    else:
        reasons.append("All applicable engineering obligations are dispositioned.")
    if open_risks:
        categories = sorted(set(item["category"] for item in open_risks))
        reasons.append(f"{len(open_risks)} documented open risk(s) remain across {', '.join(categories)}.")
    if readiness == "READY_WITH_RISK" and ledger.get("assumptions"):
        reasons.append(f"{len(ledger.get('assumptions', []))} documented assumption(s) remain for implementation awareness.")
    if readiness == "READY":
        reasons.append("No blocking clarifications, unsatisfied obligations, assumptions, or open risks remain.")
    return reasons


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


def _recommendation_reasons(recommendation: str, readiness: str, findings: List[Dict[str, Any]], open_clarifications: List[Dict[str, Any]], open_risks: List[Dict[str, Any]]) -> List[str]:
    if recommendation == "Resolve Clarifications":
        return [f"{len(open_clarifications)} clarification(s) remain open and block readiness."]
    if recommendation == "Refine Requirements":
        return ["Requirements are missing or at least one requirement lacks acceptance criteria."]
    if recommendation == "Perform Architecture Review":
        return ["Architecture obligations require clarification before implementation can responsibly begin."]
    if recommendation == "Perform Security Review":
        return ["Security obligations require clarification before implementation can responsibly begin."]
    if recommendation == "Proceed to Implementation":
        reasons = ["All applicable engineering obligations are dispositioned.", "No unresolved clarifications remain."]
        if readiness == "READY_WITH_RISK":
            categories = sorted(set(item["category"] for item in open_risks))
            reasons.append("Remaining risks are documented and non-blocking" + (f" across {', '.join(categories)}." if categories else "."))
        else:
            reasons.append("No open risks block implementation readiness.")
        return reasons
    return ["Mission planning obligations remain incomplete."]


def _mission_summary(mission: Dict[str, Any], ledger: Dict[str, Any], attributes: List[str]) -> str:
    parts = []
    stack = []
    if "TYPESCRIPT" in attributes:
        stack.append("TypeScript")
    if "NODE" in attributes:
        stack.append("Node.js")
    if stack:
        parts.append(f"This mission delivers a {' '.join(stack)} service.")
    elif "REST_API" in attributes:
        parts.append("This mission delivers a REST API service.")
    else:
        parts.append("This mission defines a software delivery effort with structured requirements and governance checks.")

    details = []
    if "HTTP_ENDPOINT" in attributes:
        details.append("an HTTP endpoint")
    if "GET_ONLY" in attributes:
        details.append("GET-only request handling")
    if "DOCKER" in attributes:
        details.append("Docker containerization")
    if "SECURE_ERROR_HANDLING" in attributes:
        details.append("secure error handling")
    if details:
        parts.append("The contract includes " + ", ".join(details) + ".")

    testing = []
    if "TESTING_REQUIRED" in attributes:
        testing.append("automated testing")
    if "MALICIOUS_TESTING" in attributes:
        testing.append("malicious-request validation")
    if testing:
        parts.append("Validation expectations include " + " and ".join(testing) + ".")

    open_count = len(_open_clarifications(ledger))
    if open_count:
        parts.append(f"{open_count} clarification(s) still need resolution before implementation readiness is complete.")
    return "\n\n".join(parts[:4])


def assess(workspace: Path) -> Dict[str, Any]:
    mission = read_yaml(workspace / "mission.yaml")
    ledger = read_yaml(workspace / "ledger.yaml")
    requirement_text = _requirement_text_with_human_answers(mission, ledger)
    requirement_assessment = assess_requirement_text(requirement_text)
    classification = classify_mission(mission, ledger, _attribute_catalog(workspace))
    attribute_sources = _attribute_sources_from_classification(classification)
    attributes = sorted(classification["detected_attributes"])
    findings = _mission_scoped_findings(evaluate_obligations(mission, ledger, attributes), requirement_assessment)
    categorized_risks = _categorized_risks(ledger)
    readiness = _readiness(ledger, findings, categorized_risks["open"])
    recommendation = _recommendation(ledger, findings, readiness)
    readiness_reason = _readiness_reasons(ledger, findings, readiness, categorized_risks["open"])
    open_clarifications = _open_clarifications(ledger)
    recommendation_reason = _recommendation_reasons(recommendation, readiness, findings, open_clarifications, categorized_risks["open"])
    obligations_total = len(findings)
    obligations_satisfied = len([item for item in findings if item["status"] == "SATISFIED"])
    obligations_needing_action = len([item for item in findings if item["status"] == "NEEDS_CLARIFICATION"])
    finding_categories = {}
    for finding in findings:
        finding_categories[finding["category"]] = finding_categories.get(finding["category"], 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp": mission.get("created_at") or "UNKNOWN",
        "mission": {
            "id": mission.get("id"),
            "title": mission.get("title"),
            "objective": mission.get("objective"),
            "prompt": mission.get("mission_prompt") or mission.get("original_prompt"),
        },
        "mission_summary": _mission_summary(mission, ledger, attributes),
        "assessment_outcome": requirement_assessment["outcome"],
        "confidence": requirement_assessment["confidence"],
        "planning_may_proceed": requirement_assessment["outcome"] in {"UNDERSTOOD", "PROCEED_WITH_ASSUMPTIONS"},
        "requirement_assessment": requirement_assessment,
        "readiness": readiness,
        "readiness_reason": readiness_reason,
        "recommendation": recommendation,
        "recommendation_reason": recommendation_reason,
        "engineering_compatibility_disclaimer": ENGINEERING_COMPATIBILITY_DISCLAIMER,
        "next_engineering_activity": recommendation,
        "mission_attributes": attributes,
        "attribute_sources": attribute_sources,
        "mission_classification": classification,
        "outstanding_clarifications": [
            {"id": item.get("id"), "question": item.get("question"), "status": item.get("status")}
            for item in open_clarifications
        ],
        "assumptions": ledger.get("assumptions", []) if isinstance(ledger.get("assumptions"), list) else [],
        "resolved_assumptions": _resolved_assumptions(ledger),
        "human_answers": ledger.get("human_answers", []) if isinstance(ledger.get("human_answers"), list) else [],
        "risks": categorized_risks["open"],
        "resolved_risks": categorized_risks["resolved"],
        "engineering_obligation_summary": {
            "total": obligations_total,
            "satisfied": obligations_satisfied,
            "needs_action": obligations_needing_action,
        },
        "discipline_findings": findings,
        "finding_categories": finding_categories,
        "rules": [
            "Open clarifications produce NOT_READY.",
            "Missing requirements produce NOT_READY.",
            "Missing acceptance criteria produce NOT_READY.",
            "Unsatisfied applicable obligations produce PARTIALLY_READY.",
            "Satisfied obligations with assumptions or risks produce READY_WITH_RISK.",
            "Satisfied obligations without assumptions or risks produce READY.",
        ],
    }


def _requirement_text_with_human_answers(mission: Dict[str, Any], ledger: Dict[str, Any]) -> str:
    prompt = mission.get("mission_prompt") or mission.get("original_prompt") or ledger.get("mission_prompt") or ""
    answers = [
        str(item.get("answer", "")).strip()
        for item in ledger.get("human_answers", [])
        if isinstance(item, dict) and item.get("answer")
    ]
    if not answers:
        return prompt
    return "\n".join([prompt, "", "Human answer context:", *[f"- {answer}" for answer in answers]])


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
        f"{item.get('id', '—')} [{item.get('category', 'Uncategorized')}]: {item.get('statement', item)}" if isinstance(item, dict) else str(item)
        for item in assessment.get("risks", [])
    ]
    resolved_risks = [
        f"{item.get('id', '—')} [{item.get('category', 'Uncategorized')}]: {item.get('statement', item)} — {item.get('resolution_reason', 'resolved')}" if isinstance(item, dict) else str(item)
        for item in assessment.get("resolved_risks", [])
    ]
    findings = [
        (
            f"{item['discipline']} — {item['obligation']} — {item['status']} "
            f"({item['severity']}, {item.get('category', 'Uncategorized')}): {item['recommendation']}"
        )
        for item in assessment.get("discipline_findings", [])
    ]
    classification = [
        (
            f"{item.get('attribute', '—')} — {item.get('decision', '—')} — "
            f"classified: {'yes' if item.get('classified') else 'no'} — "
            f"hit count: {item.get('hit_count', 0)} — threshold: {item.get('threshold', 1)} — "
            f"evidence: {_classification_evidence_text(item)}"
        )
        for item in assessment.get("mission_classification", {}).get("attributes", [])
    ]
    summary = assessment.get("engineering_obligation_summary", {})
    mission = assessment.get("mission", {})
    requirement_assessment = assessment.get("requirement_assessment", {})
    return f"""# Battalion Mission Assessment

## Mission

- **ID:** {mission.get('id', '—')}
- **Title:** {mission.get('title', '—')}
- **Objective:** {mission.get('objective', '—')}
- **Requirement:** {mission.get('prompt', '—')}

## Assessment Summary

{assessment.get('mission_summary', '—')}

## Requirement Assessment

- **Outcome:** {assessment.get('assessment_outcome', '—')}
- **Confidence:** {assessment.get('confidence', '—')}
- **Detected scale:** {requirement_assessment.get('detected_scale', '—')}
- **Detected domains:** {', '.join(requirement_assessment.get('detected_domains', [])) or '—'}
- **Planning may proceed:** {'yes' if assessment.get('planning_may_proceed') else 'no'}

### Understanding

{bullet(requirement_assessment.get('understanding', []))}

### Assessment Assumptions

{bullet(requirement_assessment.get('assumptions', []))}

### Assessment Questions

{bullet(requirement_assessment.get('questions', []))}

### Assessment Out of Scope

{bullet(requirement_assessment.get('out_of_scope', []))}

## Readiness

- **Readiness:** {assessment.get('readiness', '—')}
- **Recommendation:** {assessment.get('recommendation', '—')}

## Engineering Compatibility Disclaimer

{assessment.get('engineering_compatibility_disclaimer', ENGINEERING_COMPATIBILITY_DISCLAIMER)}

### Readiness Reasons

{bullet(assessment.get('readiness_reason', []))}

## Mission Attributes

{bullet(assessment.get('mission_attributes', []))}

## Mission Classification

{bullet(classification)}

### Attribute Sources

{bullet([f"{name}: {', '.join(sources)}" for name, sources in assessment.get('attribute_sources', {}).items()])}

## Outstanding Clarifications

{bullet(clarifications)}

## Assumptions

{bullet(assumptions)}

## Risks

{bullet(risks)}

## Resolved Risks

{bullet(resolved_risks)}

## Engineering Obligation Summary

- **Total:** {summary.get('total', 0)}
- **Satisfied:** {summary.get('satisfied', 0)}
- **Needs action:** {summary.get('needs_action', 0)}

## Finding Categories

{bullet([f"{name}: {count}" for name, count in assessment.get('finding_categories', {}).items()])}

## Discipline Findings

{bullet(findings)}

## Recommendation

{assessment.get('recommendation', '—')}

### Recommendation Rationale

{bullet(assessment.get('recommendation_reason', []))}

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


def write_mission_context_artifacts(workspace: Path, assessment: Dict[str, Any], requirement_path: str = None) -> Dict[str, Path]:
    requirement = assessment.get("mission", {}).get("prompt") or ""
    mission_id = _next_mission_context_id(workspace, requirement)
    mission_dir = workspace / "missions" / mission_id
    mission_dir.mkdir(parents=True, exist_ok=False)

    (mission_dir / "requirement.md").write_text(requirement.strip() + "\n", encoding="utf-8")
    (mission_dir / "assessment.json").write_text(json.dumps(assessment, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (mission_dir / "assessment.md").write_text(render_assessment_markdown(assessment), encoding="utf-8")
    context = build_mission_context(assessment, mission_id, requirement_path=requirement_path)
    write_yaml(mission_dir / "mission-context.yml", context)
    return {
        "mission_dir": mission_dir,
        "requirement": mission_dir / "requirement.md",
        "assessment_json": mission_dir / "assessment.json",
        "assessment_md": mission_dir / "assessment.md",
        "mission_context": mission_dir / "mission-context.yml",
    }


def build_mission_context(assessment: Dict[str, Any], mission_id: str, requirement_path: str = None) -> Dict[str, Any]:
    requirement_assessment = assessment.get("requirement_assessment", {})
    mission_type = requirement_assessment.get("mission_type", {})
    questions = requirement_assessment.get("question_details", [])
    status = "clarification_required" if requirement_assessment.get("outcome") == "CLARIFICATION_REQUIRED" else "understood"
    return {
        "schemaVersion": 1,
        "mission": {
            "id": mission_id,
            "status": status,
            "createdAt": timestamp(),
        },
        "source": {
            "requirement": assessment.get("mission", {}).get("prompt") or "",
            "requirementPath": requirement_path,
        },
        "classification": {
            "parent": mission_type.get("parent", "unknown"),
            "subtype": mission_type.get("subtype", "unknown"),
            "confidence": assessment.get("confidence", "low"),
        },
        "intent": {
            "summary": requirement_assessment.get("mission_intent", ""),
        },
        "scope": {
            "in": [_context_scope_name(value) for value in requirement_assessment.get("detected_domains", [])],
            "out": [_context_scope_name(value) for value in requirement_assessment.get("out_of_scope", [])],
        },
        "questions": {
            "unanswered": [
                {
                    "id": item.get("id"),
                    "question": item.get("question"),
                    "examples": item.get("examples", []),
                }
                for item in questions
            ] if status == "clarification_required" else [],
            "answered": [],
        },
        "assumptions": requirement_assessment.get("assumptions", []) if status == "understood" else [],
        "constraints": [],
        "notes": [],
    }


def _context_scope_name(value: str) -> str:
    return "infrastructure" if value == "infra" else value


def _next_mission_context_id(workspace: Path, requirement: str) -> str:
    missions_dir = workspace / "missions"
    missions_dir.mkdir(parents=True, exist_ok=True)
    day = timestamp()[:10]
    slug = _mission_slug(requirement)
    counter = 1
    while True:
        mission_id = f"{day}-{counter:04d}-{slug}"
        if not (missions_dir / mission_id).exists():
            return mission_id
        counter += 1


def _mission_slug(requirement: str) -> str:
    words = re.findall(r"[a-z0-9]+", requirement.lower())
    slug = "-".join(words[:5])
    return slug[:48].strip("-") or "mission"


def _classification_evidence_text(item: Dict[str, Any]) -> str:
    evidence = item.get("classification_evidence", [])
    if not evidence:
        return "None"
    return ", ".join(
        f"{entry.get('indicator', '—')} from {entry.get('source', '—')}"
        for entry in evidence
    )
