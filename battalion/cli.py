import argparse
import json
import re
import sys
from pathlib import Path

from .agents import standing_team
from .assessment import infer_attributes, write_assessment, write_mission_context_artifacts
from .assurance import assure
from .classification import write_default_attribute_catalog
from .dispatcher import DISPATCHER_ACTIONS, FAILURE_TYPES, RESULT_OUTCOMES, dispatch_next, execute_active, runtime_status
from .evidence_report import write_evidence_report
from .executor_dispatch import SUPPORTED_EXECUTORS, dispatch_engineering_brief
from .mission_analyst import generate_mission_contract, reconcile_mission_contract
from .mission_resolve import resolve_mission
from .plan_review import write_plan_review
from .reporting import render_report
from .storage import append_event, read_yaml, root, timestamp, write_yaml


DOCTRINE = ["mission_first", "evidence_over_assertion", "requirement_traceability", "zero_trust", "adversarial_review", "separation_of_duties", "human_authority", "audit_everything_material"]
NO_MISSION_MESSAGE = """Current directory does not contain a Battalion mission.

Run:

  battalion assess "Describe the mission"

or navigate to a directory containing .battalion"""


def workspace_or_exit(cwd):
    workspace = root(cwd)
    if not workspace.is_dir():
        raise SystemExit(NO_MISSION_MESSAGE)
    return workspace


def init(args, cwd):
    workspace = root(cwd)
    if workspace.exists():
        raise SystemExit("A .battalion workspace already exists.")
    mission_prompt = args.prompt or args.objective
    if not mission_prompt:
        if not sys.stdin.isatty():
            raise SystemExit("Provide --prompt or --objective when input is non-interactive.")
        mission_prompt = input("Describe the mission: ").strip()
    if not mission_prompt:
        raise SystemExit("Mission prompt cannot be empty.")
    objective = args.objective or mission_prompt
    title = args.title or objective
    workspace.mkdir(); (workspace / "reports").mkdir()
    write_yaml(workspace / "mission.yaml", {"id": "M-001", "title": title, "objective": objective, "mission_prompt": mission_prompt, "original_prompt": mission_prompt, "status": "initialized", "created_at": timestamp(), "doctrine": DOCTRINE})
    write_yaml(workspace / "agents.yaml", standing_team())
    write_default_attribute_catalog(workspace / "attributes.yml")
    write_yaml(workspace / "ledger.yaml", {"mission_id": "M-001", "mission_prompt": mission_prompt, "requirements": [], "assumptions": [], "risks": []})
    (workspace / "events.jsonl").touch()
    append_event(workspace, "mission_initialized", {"mission_id": "M-001"})
    print(f"Initialized Battalion mission at {workspace}")


def initialize_mission_workspace(cwd: Path, mission_prompt: str, title: str = None, objective: str = None):
    workspace = root(cwd)
    workspace.mkdir()
    (workspace / "reports").mkdir()
    objective = objective or mission_prompt
    title = title or objective
    write_yaml(workspace / "mission.yaml", {
        "id": "M-001",
        "title": title,
        "objective": objective,
        "mission_prompt": mission_prompt,
        "original_prompt": mission_prompt,
        "status": "initialized",
        "created_at": timestamp(),
        "doctrine": DOCTRINE,
    })
    write_yaml(workspace / "agents.yaml", standing_team())
    write_default_attribute_catalog(workspace / "attributes.yml")
    write_yaml(workspace / "ledger.yaml", {"mission_id": "M-001", "mission_prompt": mission_prompt, "requirements": [], "assumptions": [], "risks": []})
    (workspace / "events.jsonl").touch()
    append_event(workspace, "mission_initialized", {"mission_id": "M-001"})
    return workspace


def read_requirement_input(value: str, cwd: Path) -> str:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = cwd / candidate
    try:
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8").strip()
    except OSError:
        return value.strip()
    return value.strip()


def requirement_input_path(value: str, cwd: Path):
    if not value:
        return None
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = cwd / candidate
    try:
        return str(candidate) if candidate.is_file() else None
    except OSError:
        return None


def _requirement_title(requirement: str) -> str:
    first_line = next((line.strip() for line in requirement.splitlines() if line.strip()), "")
    if not first_line:
        return "Requirement Assessment"
    sentence = re.match(r"^(.+?[.!?])(?:\s|$)", first_line)
    if sentence:
        return sentence.group(1)[:120]
    return first_line[:120]


def plan(args, cwd):
    workspace = workspace_or_exit(cwd)
    statement = args.requirement
    ledger = read_yaml(workspace / "ledger.yaml")
    if not statement:
        target = generate_authoritative_plan(workspace, args.architecture or [])
        print(f"Generated execution-ready mission plan at {target}")
        return
    req_id = f"R-{len(ledger['requirements']) + 1:03d}"
    reviews = [{"reviewer": reviewer, "status": "pending"} for reviewer in (args.review or [])]
    req = {
        "id": req_id,
        "statement": statement,
        "status": "proposed",
        "owner": "mission_analyst",
        "acceptance": args.acceptance or [],
        "evidence": [],
        "assumptions": [],
        "risks": [],
        "required_reviews": reviews,
    }
    ledger["requirements"].append(req); write_yaml(workspace / "ledger.yaml", ledger)
    append_event(workspace, "requirement_added", {"requirement_id": req_id})
    append_event(workspace, "plan_created", {"requirement_count": len(ledger["requirements"])})
    print(f"Added {req_id}: {statement}")


def generate_authoritative_plan(workspace, architecture_references=None):
    assessment_path = workspace / "assessment.json"
    if not assessment_path.is_file():
        raise SystemExit("No mission assessment exists. Run battalion assess first.")
    assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    readiness = assessment.get("readiness")
    if readiness not in {"READY", "READY_WITH_RISK"}:
        raise SystemExit(f"Mission planning requires assessment readiness READY or READY_WITH_RISK. Current readiness: {readiness or 'UNKNOWN'}.")
    content = render_mission_plan(read_yaml(workspace / "mission.yaml"), read_yaml(workspace / "ledger.yaml"), assessment, architecture_references or [])
    target = workspace / "mission-plan.md"
    target.write_text(content, encoding="utf-8")
    append_event(workspace, "mission_plan_created", {
        "path": str(target.relative_to(workspace.parent)),
        "assessment_schema_version": assessment.get("schema_version"),
        "readiness": assessment.get("readiness"),
        "architecture_references": architecture_references or [],
    })
    return target


def render_mission_plan(mission, ledger, assessment, architecture_references=None):
    architecture_references = architecture_references or []
    requirements = [item for item in ledger.get("requirements", []) if isinstance(item, dict)]
    constraints = ledger.get("constraints", {}) if isinstance(ledger.get("constraints"), dict) else {}
    resolved_clarifications = [
        item for item in ledger.get("clarifications", [])
        if isinstance(item, dict) and item.get("status") in {"resolved", "superseded"}
    ]
    human_decisions = _human_decision_lines(mission, requirements, resolved_clarifications)
    lines = [
        "# Mission",
        "",
        f"**Title:** {mission.get('title', '—')}",
        "",
        _mission_statement(mission, ledger, constraints),
        "",
        "## Objective",
        "",
        _objective_line(mission),
        "",
        "## Doctrine and Constraints",
        "",
    ]
    lines.extend(_doctrine_and_constraint_lines(constraints, resolved_clarifications, architecture_references))
    if _non_empty_constraints(constraints, "technical"):
        lines.extend(["", "## Dependencies", ""])
        lines.extend(_constraint_category_lines(constraints, "technical"))
    if _non_empty_constraints(constraints, "security"):
        lines.extend(["", "## Security Requirements", ""])
        lines.extend(_constraint_category_lines(constraints, "security"))
    if _non_empty_constraints(constraints, "operational"):
        lines.extend(["", "## Operational Requirements", ""])
        lines.extend(_constraint_category_lines(constraints, "operational"))
    lines.extend([
        "",
        "## Planning Status",
        "",
    ])
    lines.extend(_planning_status_lines(assessment, human_decisions))
    lines.extend([
        "",
        "## Assumptions",
        "",
    ])
    lines.extend(_contract_item_lines(ledger.get("assumptions"), "No assumptions were identified during assessment."))
    lines.extend([
        "",
        "## Risks",
        "",
    ])
    lines.extend(_risk_lines(assessment))
    lines.extend([
        "",
        "## Human Decisions",
        "",
    ])
    lines.extend(human_decisions)
    lines.extend([
        "",
        "## Requirements",
        "",
    ])
    lines.extend(_traceable_requirement_lines(requirements))
    lines.extend([
        "",
        "## Deliverables",
        "",
    ])
    lines.extend(_deliverable_lines(mission, requirements, architecture_references))
    lines.extend([
        "",
        "## Out of Scope",
        "",
    ])
    lines.extend(_out_of_scope_lines(mission))
    lines.extend([
        "",
        "## Execution Strategy",
        "",
    ])
    lines.extend(_execution_strategy_lines(mission, requirements, constraints, architecture_references))
    lines.extend([
        "",
        "## Validation Plan",
        "",
    ])
    lines.extend(_validation_strategy_lines(requirements, constraints))
    lines.extend([
        "",
        "## Evidence Required",
        "",
    ])
    lines.extend(_evidence_required(requirements, constraints))
    lines.extend([
        "",
        "## Definition of Complete",
        "",
    ])
    lines.extend(_definition_complete_lines(requirements))
    return "\n".join(lines) + "\n"


def _mission_text(mission, ledger):
    return " ".join(str(value) for value in (
        mission.get("mission_prompt"),
        mission.get("original_prompt"),
        mission.get("objective"),
        ledger.get("mission_prompt"),
    ) if value)


def _has_text(text, pattern):
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _mission_background(mission, ledger, constraints):
    text = _mission_text(mission, ledger)
    if _has_text(text, r"\bplan template\b|\bmission-plan\.md\b"):
        return (
            "The mission exists to make Battalion's plan artifact authoritative enough to guide future implementation slices. "
            "The engineering problem is to turn doctrine into a deterministic Markdown contract that humans and executors can follow without additional verbal context."
        )
    if constraints.get("functional") and _has_text(text, r"health"):
        return (
            "The mission exists to provide a lightweight health endpoint that gives operators a dependable way to verify service availability. "
            "The engineering problem is to expose that operational signal while preserving the security and validation expectations captured in the mission contract."
        )
    if constraints.get("functional") and _has_text(text, r"\bapi\b|endpoint|http"):
        return (
            "The mission exists to deliver a defined API capability with clear request behavior and validation expectations. "
            "The engineering problem is to turn the mission contract into an implementation that behaves predictably for supported and unsupported requests."
        )
    if _has_text(text, r"\bcli\b|command[- ]line"):
        return (
            "The mission exists to deliver a command-line capability that can be executed and validated locally. "
            "The engineering problem is to provide the requested behavior with clear execution and verification boundaries."
        )
    if text:
        return "The mission exists to deliver the engineering outcome described by the mission prompt while preserving the assessed constraints, assumptions, and risks."
    return "No mission background was identified during assessment."


def _business_outcome(mission, ledger, constraints):
    text = _mission_text(mission, ledger)
    if _has_text(text, r"\bplan template\b|\bmission-plan\.md\b"):
        return "Future Battalion slices gain a stable, doctrine-aligned execution artifact that makes scope, requirements, validation, and human decisions explicit."
    if constraints.get("functional") and _has_text(text, r"health"):
        return "Operators gain a simple, automatable signal for service health, enabling faster validation of whether the service is running and responding as expected."
    if constraints.get("functional") and _has_text(text, r"\bapi\b|endpoint|http"):
        return "Consumers gain a predictable API behavior that can be implemented, tested, and validated against the mission acceptance criteria."
    if _has_text(text, r"\bcli\b|command[- ]line"):
        return "Users gain a local command-line utility that performs the requested behavior with documented validation evidence."
    return "No explicit business or operational outcome was identified during assessment."


def _mission_statement(mission, ledger, constraints):
    text = _mission_text(mission, ledger)
    if _has_text(text, r"\bplan template\b|\bmission-plan\.md\b"):
        return "Establish Battalion's canonical execution-plan contract so future slices can be handed to humans, engineers, or AI executors without extra verbal context."
    return _mission_background(mission, ledger, constraints)


def _objective_line(mission):
    text = _mission_text(mission, {"mission_prompt": ""})
    if _has_text(text, r"\bplan template\b|\bmission-plan\.md\b"):
        return "Make `battalion plan` produce a deterministic `.battalion/mission-plan.md` with the approved Plan Template v1 sections, doctrine boundaries, traceable requirements, validation plan, and human decisions."
    objective = mission.get("objective") or mission.get("mission_prompt")
    if objective:
        return objective
    return "No measurable objective was identified during assessment."


def _bullet(values, empty):
    values = values or []
    return [f"- {value}" for value in values] if values else [f"- {empty}"]


def _planning_status_lines(assessment, human_decisions):
    assumptions = assessment.get("assumptions") or []
    open_risks = assessment.get("risks") or []
    resolved_risks = assessment.get("resolved_risks") or []
    unresolved_decisions = [line for line in human_decisions if "[OPEN]" in line]
    lines = [
        f"- Open assumptions: {len(assumptions)}",
        f"- Open risks: {len(open_risks)}",
        f"- Unresolved human decisions: {len(unresolved_decisions)}",
        "- Blockers: None identified" if not assessment.get("outstanding_clarifications") else f"- Blockers: {len(assessment.get('outstanding_clarifications') or [])} outstanding clarification(s)",
    ]
    if resolved_risks:
        lines.append(f"- Resolved risks: {len(resolved_risks)}")
    return lines


def _contract_item_lines(values, empty):
    if not values:
        return [f"- {empty}"]
    result = []
    for item in values:
        if isinstance(item, dict):
            result.append(f"- {item.get('id', '—')}: {item.get('statement', item)}")
        else:
            result.append(f"- {item}")
    return result


def _constraints_overview_lines(constraints, resolved_clarifications, architecture_references):
    lines = [
        "### Doctrine",
        "- Keep mission scope limited to the assessed mission.",
        "- Preserve the boundary between Battalion recommendations and human decisions.",
        "- Prefer deterministic, source-controlled, human-readable artifacts.",
        "",
        "### Architecture",
    ]
    if architecture_references:
        lines.extend(f"- Review architecture reference filename: {name}" for name in architecture_references)
    else:
        lines.append("- No architecture reference filenames were supplied for this mission.")
    lines.extend(["", "### Technical"])
    technical = constraints.get("technical", [])
    if technical:
        lines.extend(_contract_item_lines(technical, "No technical constraints were identified during assessment."))
    else:
        lines.append("- No technical constraints were identified during assessment.")
    lines.extend(["", "### Human"])
    if resolved_clarifications:
        lines.extend(f"- {item.get('id', '—')}: {item.get('question', '—')} -> {item.get('answer', '—')}" for item in resolved_clarifications)
    else:
        lines.append("- No resolved human clarification decisions were recorded during assessment.")
    return lines


def _non_empty_constraints(constraints, category):
    return bool([item for item in constraints.get(category, []) if isinstance(item, dict) and item.get("statement")])


def _constraint_category_lines(constraints, category):
    return [f"- {item.get('id', '—')}: {item.get('statement', '—')}" for item in constraints.get(category, []) if isinstance(item, dict) and item.get("statement")]


def _doctrine_and_constraint_lines(constraints, resolved_clarifications, architecture_references):
    lines = [
        "- This Plan is the authoritative execution artifact for the mission.",
        "- Battalion owns the WHAT.",
        "- Executors own the HOW.",
        "- Battalion reports facts and may record recommendations.",
        "- Recommendations are not decisions.",
        "- Humans own engineering decisions.",
        "- Evidence Reports compare execution artifacts against Plans.",
        "- Battalion remains boring.",
        "- Battalion builds Battalion using its own artifacts.",
        "- Keep scope limited to the requirements and out-of-scope boundaries in this Plan.",
        "- Preserve deterministic, source-controlled, human-readable artifacts.",
    ]
    testing = _constraint_category_lines(constraints, "testing")
    if testing:
        lines.append("- Testing constraints:")
        lines.extend(f"  - {line[2:]}" for line in testing)
    if architecture_references:
        lines.append("- Architecture references:")
        lines.extend(f"  - {name}" for name in architecture_references)
        lines.append("- Planning records architecture reference filenames but does not inspect, validate, summarize, or interpret their contents.")
    if resolved_clarifications:
        lines.append("- Resolved human clarifications:")
        lines.extend(f"  - {item.get('id', '—')}: {item.get('question', '—')} -> {item.get('answer', '—')}" for item in resolved_clarifications)
    return lines


def _statement(value):
    if not isinstance(value, dict):
        return str(value).strip()
    return str(value.get("statement", "—")).strip().rstrip(".")


def _join_statements(values):
    statements = [_statement(item) for item in values if isinstance(item, dict)]
    return "; ".join(statement for statement in statements if statement)


def _short_excerpt(value, limit=150):
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _risk_lines(assessment):
    values = []
    values.extend(assessment.get("risks") or [])
    values.extend(assessment.get("resolved_risks") or [])
    if not values:
        return ["- No risks were identified during assessment."]
    result = []
    for item in values:
        if isinstance(item, dict):
            status = item.get("status", "OPEN")
            line = f"- {item.get('id', '—')} [{status}]: {item.get('statement', item)}"
            if status == "RESOLVED" and item.get("resolution_reason"):
                line += f" Resolution: {item['resolution_reason']}"
            result.append(line)
        else:
            result.append(f"- {item}")
    return result


def _traceable_requirement_lines(requirements):
    if not requirements:
        return ["- No traceable requirements were identified during assessment."]
    lines = []
    for requirement in requirements:
        lines.extend([
            f"### {requirement.get('id', '—')}",
            "",
            f"- Statement: {requirement.get('statement', '—')}",
            f"- Status: {requirement.get('status', '—')}",
            "- Priority: Required",
        ])
        acceptance = requirement.get("acceptance") or []
        if acceptance:
            lines.append("- Acceptance Criteria:")
            lines.extend(f"  - {item}" for item in acceptance)
        else:
            lines.append("- Acceptance Criteria: None identified during assessment.")
        trace = requirement.get("traceability", {})
        if isinstance(trace, dict) and trace.get("prompt_excerpt"):
            lines.append(f"- Source: {_short_excerpt(trace.get('prompt_excerpt'))}")
        lines.append("")
    return lines[:-1] if lines and lines[-1] == "" else lines


def _deliverable_lines(mission, requirements, architecture_references):
    text = _mission_text(mission, {"mission_prompt": ""})
    if _has_text(text, r"\bplan template\b|\bmission-plan\.md\b"):
        lines = [
            "- Updated deterministic plan renderer source.",
            "- Updated regression tests for Plan Template v1 structure and doctrine-critical language.",
            "- Updated README/template documentation identifying `.battalion/mission-plan.md` as the Plan Template v1 surface.",
            "- Regenerated `.battalion/mission-plan.md` dogfood artifact.",
            "- Concise dogfooding retrospective and validation evidence.",
        ]
    else:
        lines = [
            "- Source changes required by the traceable requirements.",
            "- Updated tests or validation assets required by the acceptance criteria.",
            "- Validation evidence mapped to requirement IDs.",
        ]
    if architecture_references:
        lines.append("- Documented review of supplied architecture references.")
    return lines


def _requirement_lines(requirements, constraints):
    selected = [
        requirement for requirement in requirements
        if not _is_non_functional_requirement(requirement)
    ]
    if not selected:
        return ["- No functional requirements were identified during assessment."]
    lines = []
    for requirement in selected:
        lines.append(f"### {requirement.get('id', '—')} — {requirement.get('statement', '—')}")
        lines.append("")
        acceptance = requirement.get("acceptance") or []
        intro = _requirement_intro(requirement, constraints)
        if intro:
            lines.append(intro)
            lines.append("")
        if acceptance:
            lines.append("Required behavior:")
            lines.extend(f"- {item}" for item in acceptance)
        else:
            lines.append("No acceptance criteria were identified during assessment.")
        trace = requirement.get("traceability", {})
        if trace.get("prompt_excerpt"):
            lines.append("")
            lines.append(f"Source: mission prompt — {_short_excerpt(trace.get('prompt_excerpt'))}")
        lines.append("")
    return lines[:-1] if lines and lines[-1] == "" else lines


def _requirement_intro(requirement, constraints):
    text = requirement.get("statement", "").lower()
    if "health endpoint" in text:
        return "The service shall expose the clarified health endpoint as an operational readiness signal. The endpoint behavior is limited to the acceptance criteria and resolved clarification decisions recorded for this mission."
    if "get-only" in text:
        return "The API shall enforce the mission's HTTP method boundary. Unsupported methods are part of the required behavior and must be handled deliberately."
    if "application" in text:
        return "The application foundation shall reflect the technologies explicitly selected by the mission and clarified during assessment."
    return ""


def _is_non_functional_requirement(requirement):
    text = f"{requirement.get('statement', '')} {' '.join(requirement.get('acceptance', []) or [])}".lower()
    return any(term in text for term in ("test", "documentation", "docker", "container", "security", "error handling", "operational", "startup"))


def _non_functional_lines(requirements, constraints):
    lines = []
    supported = []
    for requirement in requirements:
        if _is_non_functional_requirement(requirement):
            supported.append(requirement)
    for requirement in supported:
        lines.append(f"- {requirement.get('id', '—')}: {requirement.get('statement', '—')}")
    quality_map = [
        ("Security", constraints.get("security", []), bool(constraints.get("security"))),
        ("Operational readiness", constraints.get("operational", []), bool(constraints.get("operational"))),
        ("Testing", constraints.get("testing", []), bool(constraints.get("testing"))),
        ("Reliability", [], bool(constraints.get("operational"))),
        ("Observability", [], bool(constraints.get("operational"))),
        ("Maintainability", [], bool(requirements)),
        ("Performance", [], bool(constraints.get("functional"))),
    ]
    for name, values, applicable in quality_map:
        if not applicable:
            continue
        if values:
            lines.append(f"- {name}: {_join_statements(values)}.")
        else:
            lines.append(f"- {name}: No explicit {name.lower()} requirements were identified during assessment.")
    return lines


def _constraint_lines(constraints, resolved_clarifications):
    lines = []
    for category in ("functional", "technical", "security", "testing", "operational"):
        values = constraints.get(category, [])
        if not values:
            lines.append(f"- {category.title()}: No {category} constraints were identified during assessment.")
            continue
        lines.append(f"### {category.title()}")
        for item in values:
            if isinstance(item, dict):
                lines.append(f"- {item.get('id', '—')}: {item.get('statement', '—')}")
    if resolved_clarifications:
        lines.append("### Resolved Clarifications")
        for item in resolved_clarifications:
            lines.append(f"- {item.get('id', '—')}: {item.get('question', '—')} — {item.get('answer', '—')}")
    else:
        lines.append("- Resolved Clarifications: No resolved clarifications were identified during assessment.")
    return lines


def _implementation_guidance(mission, requirements, constraints, architecture_references):
    if not requirements:
        return ["No implementation guidance could be produced because no requirements were identified during assessment."]
    text = _mission_text(mission, {"mission_prompt": ""})
    lines = []
    if _has_text(text, r"\bplan template\b|\bmission-plan\.md\b"):
        lines.append("Prioritize the deterministic plan artifact contract and keep the implementation inside the existing `battalion plan` renderer.")
        lines.append("Improve the template when dogfooding exposes ambiguity, stale state, or weak executor guidance.")
        lines.append("Do not introduce a runtime template loader, review engine, evidence report change, skill system, catalog migration, integration, commit, or pull request in this slice.")
    elif constraints.get("functional") and _has_text(text, r"health"):
        lines.append("Prioritize a small, clear health-check surface that communicates service availability without broadening the API beyond the mission contract.")
    elif constraints.get("functional"):
        lines.append("Prioritize the requested API behavior and keep the implementation aligned with the functional acceptance criteria.")
    else:
        lines.append("Prioritize the primary behavior captured in the assessed mission requirements.")
    if constraints.get("security"):
        lines.append("Treat rejection behavior, malformed input, and information-disclosure controls as first-class implementation concerns rather than afterthoughts.")
    if constraints.get("operational"):
        lines.append("Preserve the operational expectations identified during assessment so the solution can be started and validated in the intended runtime context.")
    lines.append("Keep implementation choices within the mission constraints and do not add behavior that lacks traceability to the mission contract.")
    if constraints.get("technical"):
        lines.append("Honor the explicit technology constraints: " + _join_statements(constraints["technical"]) + ".")
    else:
        lines.append("No explicit technology constraints were identified during assessment.")
    if architecture_references:
        lines.append("Review and conform to the supplied architecture reference filenames before implementation; Battalion records these filenames but does not interpret their contents.")
    return [f"- {line}" for line in lines]


def _work_breakdown(requirements, constraints):
    if any("Plan Template" in requirement.get("statement", "") for requirement in requirements):
        return [
            "### Phase 1 - Artifact contract",
            "",
            "Define the required Plan Template v1 sections and doctrine boundaries in the generated mission plan.",
            "",
            "### Phase 2 - Deterministic renderer",
            "",
            "Update the existing planning renderer and mission-contract generation needed to produce a coherent plan artifact.",
            "",
            "### Phase 3 - Dogfood validation",
            "",
            "Generate `.battalion/mission-plan.md` for this slice and refine the template when the artifact exposes ambiguity or stale context.",
            "",
            "### Phase 4 - Regression and documentation",
            "",
            "Cover the generated artifact with deterministic tests and document the current Plan Template v1 surface.",
        ]
    phases = [
        ("Phase 1 — Project initialization", "Establish the application structure required by the assessed mission."),
        ("Phase 2 — Core implementation", "Implement the functional requirements and acceptance criteria."),
    ]
    if constraints.get("security"):
        phases.append(("Phase 3 — Security controls", "Implement the security constraints identified during assessment."))
    if constraints.get("operational"):
        phases.append(("Phase 4 — Operational readiness", "Implement deployment, startup, and operational expectations identified during assessment."))
    if constraints.get("testing") or requirements:
        phases.append(("Phase 5 — Validation", "Run tests and validate acceptance criteria against produced evidence."))
    lines = []
    for title, description in phases:
        lines.extend([f"### {title}", "", description, ""])
    return lines[:-1]


def _execution_strategy_lines(mission, requirements, constraints, architecture_references):
    text = _mission_text(mission, {"mission_prompt": ""})
    if _has_text(text, r"\bplan template\b|\bmission-plan\.md\b"):
        return [
            "1. Define the canonical Plan Template v1 information model and section order.",
            "2. Refactor the renderer so Mission, Objective, Requirements, Validation, Evidence, and Completion each have one clear job.",
            "3. Remove readiness classifications, duplicated mission text, empty boilerplate, fabricated review roles, and generic requirement prose from the Plan artifact.",
            "4. Regenerate this dogfood mission with the revised renderer and inspect whether the artifact can be read once and executed without extra context.",
            "5. Add or update deterministic tests that assert section order, doctrine-critical language, requirement traceability, and omitted out-of-scope systems.",
            "6. Update documentation for the current `.battalion/mission-plan.md` Plan Template v1 surface.",
            "7. Run the full deterministic test suite and record validation evidence.",
        ]
    lines = [
        "1. Review the authoritative Plan and resolve any open human decisions that block implementation.",
        "2. Implement only the traceable requirements and deliverables recorded in this Plan.",
        "3. Produce deterministic validation evidence mapped to requirement IDs.",
        "4. Record any unable-to-verify findings for human disposition.",
    ]
    if not architecture_references:
        lines[0] = "1. Review the authoritative Plan and resolve any open human decisions that block implementation."
    if not requirements:
        lines.insert(2, "3. Stop before implementation if no traceable requirements are available.")
    if constraints.get("security"):
        lines.append("5. Treat security constraints as required validation targets, not optional review notes.")
    return lines


def _testing_strategy(requirements, constraints):
    lines = []
    testing = constraints.get("testing", [])
    lines.append("- Validate the core functional behavior against each acceptance criterion in the mission contract.")
    statements = " ".join(item.get("statement", "") for item in testing if isinstance(item, dict)).lower()
    if "happy-path" in statements:
        lines.append("- Cover the successful request path to prove the expected behavior works under normal input.")
    if "negative-path" in statements or constraints.get("security"):
        lines.append("- Cover negative paths for invalid, unsupported, or rejected requests.")
    if "malicious-request" in statements or any("malformed" in item.get("statement", "").lower() for item in constraints.get("security", []) if isinstance(item, dict)):
        lines.append("- Cover malicious or malformed input to verify safe rejection and no information disclosure.")
    acceptance_count = sum(1 for requirement in requirements if requirement.get("acceptance"))
    if acceptance_count:
        lines.append("- Map test evidence directly to the acceptance criteria for each requirement.")
    if constraints.get("security"):
        lines.append("- Include security validation for the explicit security constraints identified during assessment.")
    if constraints.get("operational"):
        lines.append("- Include operational validation that proves startup and runtime expectations are met.")
    if not testing and not constraints.get("security") and not constraints.get("operational"):
        lines.append("- No additional specialized testing constraints were identified during assessment.")
    return lines


def _validation_strategy_lines(requirements, constraints):
    lines = [
        "- Deterministic validation must prove each requirement by ID or report that it is unable to verify it.",
        "- Validation evidence must be reproducible from source-controlled commands, files, or runtime observations.",
        "- Human decisions are required for judgment calls that deterministic checks cannot prove.",
    ]
    if requirements:
        for requirement in requirements:
            lines.append(f"- {requirement.get('id', '—')}: validate acceptance criteria recorded in Requirements.")
    if constraints.get("testing"):
        lines.append("- Testing constraints must be covered by automated tests or explicitly dispositioned.")
    return lines


def _evidence_required(requirements, constraints):
    lines = ["- Requirement evidence mapped by ID."]
    if constraints.get("testing"):
        lines.append("- Passing automated test output.")
    if constraints.get("technical"):
        lines.append("- Successful build or execution evidence for the specified technology stack.")
    if constraints.get("operational"):
        lines.append("- Operational validation evidence for applicable runtime expectations.")
    if any("docker" in item.get("statement", "").lower() or "container" in item.get("statement", "").lower() for item in constraints.get("technical", []) + constraints.get("operational", []) if isinstance(item, dict)):
        lines.append("- Container build and run evidence.")
    lines.append("- Human decision evidence for any accepted risk, deferral, rejection, or final approval.")
    lines.append("- PR approval or PR merge may satisfy human decision evidence when observed; manual artifact updates are an optional fallback for workflows without a PR.")
    lines.append("- Passing tests, implementation completion, and Battalion recommendations must not be inferred as human approval.")
    return lines


def _human_decision_lines(mission, requirements, resolved_clarifications):
    text = _mission_text(mission, {"mission_prompt": ""})
    lines = [
        "- Humans decide whether to proceed, accept risk, defer, reject, or approve the work.",
        "- Battalion recommendations are advisory signals, not approvals.",
        "- Human decisions must have deterministic evidence, but manual Plan or evidence edits are not the default completion mechanism.",
        "- PR approval may satisfy human review evidence when observed.",
        "- PR merge may satisfy authorization or completion evidence when observed.",
        "- Manual artifact updates remain an optional fallback for workflows without a PR.",
        "- Passing tests, implementation completion, and Battalion recommendations must never be inferred as human approval.",
    ]
    if _has_text(text, r"\bplan template\b|\bmission-plan\.md\b"):
        lines.extend([
            "- HD-001 [OPEN]: Approve the final section set and order for Plan Template v1.",
            "- HD-002 [OPEN]: Approve removal of readiness classifications from the Plan artifact.",
            "- HD-003 [OPEN]: Decide whether the revised artifact is accepted as Battalion's canonical planning surface.",
        ])
    else:
        lines.append("- HD-001 [OPEN]: Decide whether the completed implementation satisfies this Plan.")
    if resolved_clarifications:
        lines.append("- Resolved clarification decisions are human decision records for this Plan.")
    return lines


def _definition_complete_lines(requirements):
    lines = [
        "- Every traceable requirement has implementation evidence or an explicit human disposition.",
        "- Every acceptance criterion has deterministic validation evidence or an explicit unable-to-verify finding.",
        "- Human decisions listed in this Plan have deterministic evidence from PR approval, PR merge, or an explicit manual fallback record.",
        "- The final human decision is recorded outside Battalion recommendations.",
    ]
    if not requirements:
        lines.insert(0, "- No implementation should close until traceable requirements exist.")
    return lines


def _out_of_scope_lines(mission):
    text = _mission_text(mission, {"mission_prompt": ""})
    if _has_text(text, r"\bplan template\b|\bmission-plan\.md\b"):
        return [
            "- Review engines.",
            "- Evidence Report changes.",
            "- Skill systems.",
            "- Catalog migration.",
            "- Integrations.",
            "- Runtime template loader.",
            "- Dispatch behavior changes.",
            "- Commit, push, merge, or pull request work unless explicitly authorized.",
        ]
    return [
        "- Planning does not dispatch work.",
        "- Planning does not execute work.",
        "- Planning does not invoke AI.",
    ]


def _success_criteria(mission, requirements, constraints):
    if not requirements:
        return ["- No mission success criteria could be derived because no requirements were identified during assessment."]
    text = _mission_text(mission, {"mission_prompt": ""})
    lines = []
    if _has_text(text, r"\bplan template\b|\bmission-plan\.md\b"):
        lines.append("- `battalion plan` produces a deterministic `.battalion/mission-plan.md` artifact with the required Plan Template v1 sections.")
        lines.append("- The generated plan clearly separates Battalion recommendations from human decisions.")
        lines.append("- Regression tests and documentation support the current Plan Template v1 contract without adding out-of-scope systems.")
        return lines
    if constraints.get("functional") and _has_text(text, r"health"):
        lines.append("- The service exposes the specified health endpoint and returns the expected successful response for valid GET requests.")
    elif constraints.get("functional"):
        lines.append("- The delivered API behavior matches the functional requirements and clarified request contract.")
    else:
        lines.append("- The delivered solution performs the primary behavior described by the mission contract.")
    if constraints.get("security"):
        lines.append("- Unsupported, invalid, or malicious interactions are handled according to the recorded security constraints without exposing implementation details.")
    if constraints.get("testing"):
        lines.append("- Happy-path, negative-path, and applicable malicious-input validation produce reproducible evidence.")
    else:
        lines.append("- Validation evidence demonstrates that the acceptance criteria have been met.")
    if constraints.get("operational"):
        lines.append("- Operational evidence shows the solution starts and runs in the required runtime or packaging context.")
    return lines


def _clarification_action(value, status):
    clarification_id, separator, answer = value.partition("=")
    if not separator or not clarification_id.strip() or not answer.strip():
        raise SystemExit(f"Clarification actions must use Q-ID=value syntax: {value}")
    return clarification_id.strip(), status, answer.strip()


def apply_clarification_actions(workspace, ledger, actions, resolver):
    clarifications = ledger.get("clarifications")
    by_id = {item.get("id"): item for item in clarifications}
    action_time = timestamp()
    audit_events = []
    for clarification_id, status, answer in actions:
        item = by_id.get(clarification_id)
        if item is None:
            raise SystemExit(f"Unknown clarification: {clarification_id}")
        previous_status = item.get("status")
        allowed = previous_status == "open" or (previous_status == "resolved" and status == "superseded")
        if not allowed:
            raise SystemExit(f"{clarification_id} cannot transition from {previous_status} to {status}.")
        item.update(status=status, answer=answer, resolved_by=resolver, resolved_at=action_time)
        item.setdefault("history", []).append({
            "action": status,
            "status": status,
            "value": answer,
            "actor": resolver,
            "timestamp": action_time,
        })
        audit_events.append((f"clarification_{status}", {
            "mission_id": ledger.get("mission_id"),
            "clarification_id": clarification_id,
            "action": status,
            "previous_status": previous_status,
            "value": answer,
            "resolver": resolver,
        }))

    updated_requirements = reconcile_mission_contract(ledger)
    mission = read_yaml(workspace / "mission.yaml")
    ledger["mission_attributes"] = infer_attributes(mission, ledger)
    write_yaml(workspace / "ledger.yaml", ledger)
    for event_type, details in audit_events:
        append_event(workspace, event_type, details, actor=resolver)
    append_event(workspace, "mission_contract_reconciled", {
        "mission_id": ledger.get("mission_id"),
        "clarification_ids": [clarification_id for clarification_id, _, _ in actions],
        "updated_requirements": updated_requirements,
    }, actor="mission_analyst")
    return updated_requirements


def clarify(args, cwd):
    workspace = workspace_or_exit(cwd)
    ledger = read_yaml(workspace / "ledger.yaml")
    clarifications = ledger.get("clarifications")
    if not isinstance(clarifications, list):
        raise SystemExit("Mission contract does not contain a valid clarifications list. Run 'battalion assess' first.")
    open_items = [item for item in clarifications if item.get("status") == "open"]
    print(f"Clarifications: {len(open_items)} open, {sum(item.get('status') == 'resolved' for item in clarifications)} resolved")
    print_open_clarifications(open_items)

    actions = []
    actions.extend(_clarification_action(value, "resolved") for value in (args.answer or []))
    actions.extend(_clarification_action(value, "rejected") for value in (args.reject or []))
    actions.extend(_clarification_action(value, "superseded") for value in (args.supersede or []))
    resolver = args.resolver
    if not actions:
        if not open_items:
            print("\nNo open clarifications require answers.")
            return
        if not sys.stdin.isatty():
            raise SystemExit("Provide --answer Q-ID=value and --resolver when input is non-interactive.")
        actions = collect_clarification_actions(open_items)
        if actions and not resolver:
            resolver = prompt_user("\nResolved by: ").strip()
    elif not resolver and sys.stdin.isatty():
        resolver = prompt_user("Resolved by: ").strip()
    if actions and not resolver:
        raise SystemExit("Provide --resolver for clarification actions.")
    if not actions:
        print(f"\nSummary: 0 resolved, {len(open_items)} still open.")
        return

    updated_requirements = apply_clarification_actions(workspace, ledger, actions, resolver)
    remaining_open = sum(item.get("status") == "open" for item in clarifications)
    resolved_count = sum(status == "resolved" for _, status, _ in actions)
    print(f"\nApplied {len(actions)} clarification action(s); reconciled {len(updated_requirements)} requirement(s).")
    print(f"Summary: {resolved_count} resolved, {remaining_open} still open.")


def print_open_clarifications(open_items):
    if not open_items:
        return
    for item in open_items:
        print(f"\n{item['id']}\n{item['question']}\nAnswer: {item.get('answer') or 'None'}")


def prompt_user(message):
    try:
        return input(message)
    except EOFError:
        return ""


def collect_clarification_actions(open_items):
    actions = []
    while True:
        choice = prompt_user("\nClarify action: [a]nswer all, answer [o]ne, [s]kip, [e]xit\n> ").strip().lower()
        if choice in {"", "s", "skip"}:
            return actions
        if choice in {"e", "exit", "q", "quit"}:
            return actions
        if choice in {"a", "all", "answer all"}:
            for item in open_items:
                if any(existing_id == item["id"] for existing_id, _, _ in actions):
                    continue
                answer = prompt_user(f"\n{item['id']} — {item['question']}\nPress Enter to skip.\n> ").strip()
                if answer:
                    actions.append((item["id"], "resolved", answer))
            return actions
        if choice in {"o", "one", "answer one"}:
            clarification_id = prompt_user("Clarification ID: ").strip()
            item = next((entry for entry in open_items if entry.get("id") == clarification_id), None)
            if item is None:
                print(f"Unknown open clarification: {clarification_id}")
                continue
            answer = prompt_user(f"\n{item['id']} — {item['question']}\nPress Enter to skip.\n> ").strip()
            if answer:
                actions.append((item["id"], "resolved", answer))
            return actions
        print("Choose answer all, answer one, skip, or exit.")


def dispatch(args, cwd):
    workspace = workspace_or_exit(cwd)
    if args.executor:
        try:
            dispatch_engineering_brief(workspace, args.executor, args.mode)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return
    try:
        result = dispatch_next(workspace, allow_implementation_before_reviews=args.allow_implementation_before_reviews)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    assignment = result["assignment"]
    if assignment is None:
        print("Dispatcher found no dispatchable work.")
        print(f"Decision: {result['decision']}")
        return
    if result["decision"] == "halt_for_blocker":
        action = "Blocked by"
    else:
        action = "Created" if result["created"] else "Continuing"
    print(f"{action} assignment {assignment['id']}")
    print(f"Requirement: {assignment['requirement_id']}")
    print(f"Unit: {assignment['assigned_unit']}")
    print(f"Type: {assignment['assignment_type']}")
    if assignment.get("reviewer"):
        print(f"Reviewer: {assignment['reviewer']}")
    print(f"Status: {assignment['status']}")
    print(f"Decision: {result['decision']}")


def execute(args, cwd):
    workspace = workspace_or_exit(cwd)
    try:
        result = execute_active(
            workspace,
            outcome=args.outcome,
            summary=args.summary,
            evidence=args.evidence or [],
            failure_type=args.failure_type,
            reason=args.reason or "",
            impact=args.impact or "",
            recommendation=args.recommendation or "",
            decision_action=args.decision_action,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    assignment = result["assignment"]
    print(f"Executed assignment {assignment['id']}")
    print(f"Outcome: {assignment['result_packet']['outcome']}")
    print(f"Status: {assignment['status']}")
    if assignment.get("abort_packet"):
        print(f"Failure Type: {assignment['abort_packet']['failure_type']}")
        print(f"Reason: {assignment['abort_packet']['reason']}")
    print(f"Dispatcher Decision: {result['decision']['action']}")
    print(f"Recommendation: {result['decision']['recommendation']}")
    next_assignment = result.get("next_assignment")
    if next_assignment:
        print(f"Next Assignment: {next_assignment['id']} -> {next_assignment['assigned_unit']}")


def status(args, cwd):
    workspace = workspace_or_exit(cwd)
    try:
        state = runtime_status(workspace)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    assignments = state["assignments"]
    clarifications = state["clarifications"]
    print(f"Mission: {state['mission']['title']}")
    print(f"Current phase: {state['current_phase']}")
    print("Assignments:")
    if assignments:
        for assignment in assignments:
            print(f"- {assignment['id']} {assignment['status']} {assignment['assigned_unit']} -> {assignment['requirement_id']}")
    else:
        print("- None")
    print("Blocked work:")
    if state["blocked_work"]:
        for assignment in state["blocked_work"]:
            print(f"- {assignment['id']} {assignment['status']}: {assignment.get('abort_packet', {}).get('reason', 'blocked')}")
    else:
        print("- None")
    print("Completed work:")
    if state["completed_work"]:
        for assignment in state["completed_work"]:
            print(f"- {assignment['id']} -> {assignment['requirement_id']}")
    else:
        print("- None")
    print("Pending work:")
    if state["pending_work"]:
        for requirement in state["pending_work"]:
            print(f"- {requirement.get('id', '—')} {requirement.get('status', '—')}: {requirement.get('statement', '—')}")
    else:
        print("- None")
    print("Clarifications:")
    if clarifications:
        for clarification in clarifications:
            print(f"- {clarification.get('id', '—')} {clarification.get('status', '—')}: {clarification.get('question', '—')}")
    else:
        print("- None")
    print(f"Recommendation: {state['recommendation']}")


def assessment(args, cwd):
    args.question_budget = 5
    requirement_value = args.requirement_text or args.requirement
    requirement_path = None
    workspace = root(cwd)
    if requirement_value:
        requirement_path = requirement_input_path(requirement_value, cwd)
        requirement = read_requirement_input(requirement_value, cwd)
        if not requirement:
            raise SystemExit("Requirement cannot be empty.")
        workspace = set_assessment_requirement(cwd, requirement)
    elif not workspace.exists():
        if not sys.stdin.isatty():
            raise SystemExit("Provide a requirement, for example: battalion assess \"Create a README\"")
        print("What would you like Battalion to assess?")
        requirement = prompt_user("> ").strip()
        if not requirement:
            raise SystemExit("Requirement cannot be empty.")
        workspace = set_assessment_requirement(cwd, requirement)
    try:
        ensure_assessed_contract(workspace)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        result = write_assessment(workspace)
        if resolve_requirement_questions(workspace, args, result):
            ensure_assessed_contract(workspace)
            result = write_assessment(workspace)
        if resolve_assessment_clarifications(workspace, args, result):
            result = write_assessment(workspace)
            if resolve_requirement_questions(workspace, args, result):
                ensure_assessed_contract(workspace)
                result = write_assessment(workspace)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print_assessment_summary(result)
    artifacts = write_mission_context_artifacts(workspace, result, requirement_path=requirement_path)
    print("\nArtifacts")
    print(f"- Mission Context: {artifacts['mission_context'].relative_to(cwd)}")
    print(f"- Assessment Report: {artifacts['assessment_md'].relative_to(cwd)}")
    if result.get("readiness") in {"READY", "READY_WITH_RISK"}:
        plan_path = generate_authoritative_plan(workspace)
        print(f"- Authoritative Plan: {plan_path.relative_to(cwd)}")


def set_assessment_requirement(cwd: Path, requirement: str):
    workspace = root(cwd)
    if not workspace.exists():
        return initialize_mission_workspace(cwd, requirement, title=_requirement_title(requirement), objective=requirement)
    mission = read_yaml(workspace / "mission.yaml")
    mission["title"] = _requirement_title(requirement)
    mission["objective"] = requirement
    mission["mission_prompt"] = requirement
    mission["original_prompt"] = requirement
    write_yaml(workspace / "mission.yaml", mission)
    write_yaml(workspace / "ledger.yaml", {"mission_id": mission.get("id", "M-001"), "mission_prompt": requirement, "requirements": [], "assumptions": [], "risks": []})
    append_event(workspace, "assessment_requirement_updated", {"mission_id": mission.get("id", "M-001")})
    for stale_artifact in ("assessment.json", "assessment.md", "mission-plan.md"):
        target = workspace / stale_artifact
        if target.exists():
            target.unlink()
    return workspace


def print_assessment_summary(result):
    requirement_assessment = result.get("requirement_assessment", {})
    print("Assessment Result")
    print("-----------------")
    print(result.get("assessment_outcome", result.get("readiness", "UNKNOWN")))
    confidence = result.get("confidence", "—")
    print(f"\nConfidence: {confidence.title() if isinstance(confidence, str) else confidence}")
    mission_type = requirement_assessment.get("mission_type", {})
    print("\nMission Type")
    print(mission_type.get("display", "Unknown / Unknown"))
    print("\nMission Intent")
    print(requirement_assessment.get("mission_intent", "Mission intent is not yet understood."))
    print("\nUnderstanding")
    for item in requirement_assessment.get("understanding", []) or ["None"]:
        print(f"- {item}")
    questions = requirement_assessment.get("questions", [])
    if not questions:
        print("\nAssumptions")
        for item in requirement_assessment.get("assumptions", []) or ["None"]:
            print(f"- {item}")
    print("\nQuestions")
    if questions:
        for index, item in enumerate(questions, start=1):
            print(_format_assessment_question(index, item))
    else:
        print("- None")
    print(f"\nRecommendation\n{requirement_assessment.get('recommendation', result.get('recommendation', '—'))}")


def _assessment_display_label(value):
    labels = {
        "api": "API",
        "ui": "UI",
        "infra": "Infrastructure",
        "data": "Data",
        "documentation": "Documentation",
        "testing": "Testing",
        "security": "Security",
        "unknown": "Unknown",
        "task": "Task",
        "slice": "Slice",
        "user_story": "User Story",
        "feature": "Feature",
        "epic": "Epic",
    }
    if not isinstance(value, str):
        return str(value)
    return labels.get(value, value.replace("_", " ").title())


def _format_assessment_question(index, item):
    text = str(item)
    if " Examples: " not in text:
        return f"{index}. {text}"
    question, examples = text.split(" Examples: ", 1)
    return f"{index}. {question}\n   Examples: {examples}"


def primary_assessment_findings(result):
    findings = []
    for item in result.get("discipline_findings", []):
        if item.get("status") != "NEEDS_CLARIFICATION":
            continue
        findings.append(_plain_finding(item.get("recommendation") or item.get("description") or item.get("obligation")))
    for risk in result.get("risks", []):
        if isinstance(risk, dict):
            findings.append(risk.get("statement", "Review documented risk."))
    if not findings and result.get("readiness") in {"READY", "READY_WITH_RISK"}:
        findings.append("No blocking readiness findings remain.")
    if not findings:
        findings.append("No primary findings.")
    deduped = []
    for finding in findings:
        if finding and finding not in deduped:
            deduped.append(finding)
    return deduped[:6]


def _plain_finding(message):
    mapping = {
        "Identify implementation technology before implementation begins.": "Implementation technology has not been selected.",
        "Identify implementation technology before coding begins.": "Implementation technology has not been selected.",
        "Confirm runtime selection before implementation begins.": "Runtime selection has not been confirmed.",
        "Identify the deployment or execution environment before implementation begins.": "Deployment environment is unspecified.",
        "Define the API contract before implementation begins.": "API contract details are incomplete.",
        "Define endpoint path and HTTP method expectations before implementation begins.": "HTTP endpoint contract details are incomplete.",
        "Specify secure error-handling expectations before implementation begins.": "Secure error-handling expectations are unspecified.",
        "Specify authentication disposition before implementation begins.": "Authentication expectations are unspecified.",
        "Specify authorization disposition before implementation begins.": "Authorization expectations are unspecified.",
        "Resolve open clarifications before implementation begins.": "Open clarifications must be resolved before planning.",
    }
    return mapping.get(message, message or "Review readiness finding.")


def ensure_assessed_contract(workspace):
    ledger = read_yaml(workspace / "ledger.yaml")
    if isinstance(ledger.get("requirements"), list) and ledger["requirements"]:
        return
    mission = read_yaml(workspace / "mission.yaml")
    mission_prompt = mission.get("mission_prompt") or mission.get("original_prompt")
    if not isinstance(mission_prompt, str) or not mission_prompt.strip():
        raise ValueError("Mission prompt is missing or invalid. Reinitialize the mission with a valid prompt.")
    contract_prompt = _assessment_context_text(mission_prompt, ledger)
    contract = generate_mission_contract(mission["id"], contract_prompt, timestamp())
    contract["mission_prompt"] = mission_prompt
    contract["human_answers"] = ledger.get("human_answers", [])
    _normalize_trace_excerpts(contract, mission_prompt)
    contract["mission_attributes"] = infer_attributes(mission, contract)
    write_yaml(workspace / "ledger.yaml", contract)
    append_event(workspace, "mission_contract_generated", {
        "mission_id": mission["id"],
        "generated_by": "mission_assessment",
        "requirement_ids": [requirement["id"] for requirement in contract["requirements"]],
        "assumption_count": len(contract["assumptions"]),
        "risk_count": len(contract["risks"]),
        "clarification_count": len(contract["clarifications"]),
        "constraint_count": sum(len(values) for values in contract["constraints"].values()),
    })
    for clarification in contract["clarifications"]:
        append_event(workspace, "clarification_created", {
            "mission_id": mission["id"],
            "clarification_id": clarification["id"],
            "action": "created",
            "value": clarification["question"],
        }, actor="mission_analyst")


def resolve_requirement_questions(workspace, args, assessment_result):
    requirement_assessment = assessment_result.get("requirement_assessment", {})
    questions = requirement_assessment.get("questions", [])
    if not questions:
        return False
    if not sys.stdin.isatty():
        return False
    budget = max(0, getattr(args, "question_budget", 5))
    if budget == 0:
        return False
    question_details = requirement_assessment.get("question_details", [])
    selected = []
    for index, question in enumerate(questions[:budget]):
        detail = question_details[index] if index < len(question_details) else {}
        selected.append({
            "id": detail.get("id") or f"assessment.{index + 1}",
            "question": detail.get("question") or _question_without_examples(question),
            "display": question,
        })
    args.question_budget = budget - len(selected)
    print(f"\nAssessment needs {len(selected)} human answer(s) before it can produce the authoritative Plan.")
    answers = []
    for index, item in enumerate(selected, start=1):
        print(f"\nQuestion {index} of {len(selected)}")
        print(_clean_question_text(item["display"]))
        answer = prompt_user("> ").strip()
        if answer:
            answers.append({**item, "answer": answer})
    if not answers:
        print("\nNo answers provided; assessment remains incomplete.")
        return False
    mission = read_yaml(workspace / "mission.yaml")
    ledger = read_yaml(workspace / "ledger.yaml")
    ledger["human_answers"] = _merge_human_answers(ledger.get("human_answers", []), answers, args.resolver or "human")
    ledger["requirements"] = []
    ledger["assumptions"] = []
    ledger["risks"] = []
    ledger["clarifications"] = []
    ledger["mission_prompt"] = mission.get("original_prompt") or mission.get("mission_prompt") or ledger.get("mission_prompt", "")
    write_yaml(workspace / "ledger.yaml", ledger)
    append_event(workspace, "assessment_questions_answered", {
        "mission_id": mission.get("id", "M-001"),
        "answered_count": len(answers),
        "question_count": len(selected),
        "answer_ids": [item["id"] for item in answers],
    }, actor=args.resolver or "human")
    print(f"\nCaptured {len(answers)} answer(s). Re-running assessment.")
    return True


def _clean_question_text(question):
    text = str(question)
    return text.replace(" Examples: ", "\nExamples: ")


def _question_without_examples(question):
    text = str(question)
    return text.split(" Examples: ", 1)[0].strip()


def _merge_human_answers(existing, answers, resolver):
    ordered = [
        item
        for item in existing
        if isinstance(item, dict) and item.get("id")
    ] if isinstance(existing, list) else []
    by_id = {item["id"]: item for item in ordered}
    for item in answers:
        record = {
            "id": item["id"],
            "question": item["question"],
            "answer": item["answer"],
            "status": "resolved",
            "answered_by": resolver,
            "answered_at": timestamp(),
        }
        if item["id"] not in by_id:
            ordered.append(record)
        else:
            ordered = [record if existing_item.get("id") == item["id"] else existing_item for existing_item in ordered]
        by_id[item["id"]] = record
    return ordered


def _assessment_context_text(mission_prompt, ledger):
    answers = [
        item.get("answer", "").strip()
        for item in ledger.get("human_answers", [])
        if isinstance(item, dict) and item.get("answer")
    ]
    if not answers:
        return mission_prompt
    return "\n".join([mission_prompt, "", "Human answer context:", *[f"- {answer}" for answer in answers]])


def _normalize_trace_excerpts(contract, mission_prompt):
    def visit(value):
        if isinstance(value, dict):
            trace = value.get("traceability")
            if isinstance(trace, dict):
                excerpt = trace.get("prompt_excerpt")
                if isinstance(excerpt, str) and excerpt and excerpt not in mission_prompt:
                    trace["prompt_excerpt"] = mission_prompt
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(contract)


def resolve_assessment_clarifications(workspace, args, assessment_result):
    ledger = read_yaml(workspace / "ledger.yaml")
    clarifications = ledger.get("clarifications", [])
    if not isinstance(clarifications, list):
        return False
    open_items = [item for item in clarifications if isinstance(item, dict) and item.get("status") == "open"]
    if not open_items:
        return False
    if not sys.stdin.isatty():
        return False
    budget = max(0, getattr(args, "question_budget", 5))
    if budget == 0:
        return False
    selected = open_items[:budget]
    args.question_budget = budget - len(selected)
    print(f"\nAssessment needs {len(selected)} human answer(s) before it can produce the authoritative Plan.")
    actions = []
    for index, item in enumerate(selected, start=1):
        print(f"\nQuestion {index} of {len(selected)}")
        print(item.get("question", "Provide the missing decision."))
        answer = prompt_user("> ").strip()
        if answer:
            actions.append((item["id"], "resolved", answer))
    if not actions:
        print("\nNo answers provided; assessment remains incomplete.")
        return False
    resolver = args.resolver or "human"
    apply_clarification_actions(workspace, ledger, actions, resolver)
    print(f"\nCaptured {len(actions)} answer(s). Re-running assessment.")
    return True


def assurance(args, cwd):
    workspace = workspace_or_exit(cwd)
    result = assure(workspace, run=args.run)
    if (workspace / "events.jsonl").is_file(): append_event(workspace, "assurance_completed", result.to_dict())
    counts = result.clarification_counts
    engineering = result.engineering_result or {}
    summary = engineering.get("summary", {})
    print("Mission Assurance")
    print(f"\nEngineering Result: {engineering.get('status', result.status)}")
    print(f"Recommendation: {result.recommendation}")
    print("\nSummary:")
    print(f"- Verified: {summary.get('verified', 0)}")
    print(f"- Failed: {summary.get('failed', 0)}")
    print(f"- Unable to verify: {summary.get('unable_to_verify', 0)}")
    print(f"- Runtime Checks: {summary.get('runtime_checks', 0)}")
    print(f"- Static Checks: {summary.get('static_checks', 0)}")
    if args.run:
        print("\nRuntime Target:")
        targets = engineering.get("runtime_targets", [])
        if targets:
            for target in targets:
                print(f"- Base URL: {target.get('base_url', '—')}")
                print(f"  Endpoint: {target.get('endpoint', '—')}")
                print(f"  Full URL: {target.get('full_url', '—')}")
        else:
            print("- None detected")
        diagnostics = engineering.get("diagnostics", [])
        if diagnostics:
            print("\nDiagnostics:")
            for diagnostic in diagnostics:
                print(f"- {diagnostic}")
    for title, state in (("Failed", "FAILED"), ("Unable to verify", "UNABLE_TO_VERIFY")):
        print(f"\n{title}:")
        checks = [check for check in engineering.get("checks", []) if check.get("result") == state]
        if checks:
            for check in checks:
                print(f"- Requirement: {check.get('requirement_id', '—')}")
                print(f"  Criterion: {check.get('criterion', '—')}")
                print(f"  Result: {check.get('result', '—')}")
                print(f"  Evidence: {_format_evidence(check.get('evidence'), verbose=args.verbose)}")
                print(f"  Expected: {json.dumps(check.get('expected'), sort_keys=True)}")
                print(f"  Observed: {json.dumps(check.get('observed'), sort_keys=True)}")
                print(f"  Finding: {check.get('finding', '—')}")
                print(f"  Recommendation: {check.get('recommendation', '—')}")
                for diagnostic in check.get("diagnostics", []) or []:
                    print(f"  Diagnostic: {diagnostic}")
        else:
            print("- None")
    print("\nGovernance:")
    print(f"- Result: {result.governance_result.get('status', result.status) if result.governance_result else result.status}")
    print(
        f"- Clarifications: {counts.get('open', 0)} open, {counts.get('resolved', 0)} resolved, "
        f"{counts.get('superseded', 0)} superseded, {counts.get('rejected', 0)} rejected"
    )
    governance_findings = (result.governance_result or {}).get("findings", [])
    if governance_findings:
        for finding in governance_findings:
            print(f"- {finding}")
    else:
        print("- None")
    print("\nOverall:")
    print(f"- Status: {result.status}")
    print(f"- Recommendation: {result.recommendation}")
    print(f"- Confidence: {result.confidence}")
    print("\nArtifacts:")
    print(f"- {workspace / 'assurance.json'}")
    print(f"- {workspace / 'assurance.md'}")


def _format_evidence(evidence, verbose=False):
    if verbose:
        return json.dumps(evidence, sort_keys=True)
    if not evidence:
        return "None"
    values = []
    for item in evidence:
        if isinstance(item, dict) and item.get("type") == "http_response":
            parts = []
            if item.get("url"):
                parts.append(f"url={item['url']}")
            if item.get("status_code") is not None:
                parts.append(f"status={item['status_code']}")
            if item.get("error"):
                parts.append(f"error={item['error']}")
            body = item.get("body")
            if isinstance(body, str) and len(body) <= 120:
                parts.append(f"body={body}")
            elif isinstance(body, str):
                parts.append(f"body={body[:117]}...")
            values.append("HTTP response (" + ", ".join(parts) + ")")
        else:
            values.append(str(item))
    return "; ".join(values)


def report(args, cwd):
    workspace = workspace_or_exit(cwd)
    try: content = render_report(workspace)
    except ValueError as exc: raise SystemExit(str(exc)) from exc
    target = workspace / "reports" / "mission-report.md"; target.parent.mkdir(exist_ok=True); target.write_text(content, encoding="utf-8")
    append_event(workspace, "report_generated", {"path": str(target.relative_to(cwd))})
    print(f"Generated {target}")


def resolve(args, cwd):
    workspace = workspace_or_exit(cwd)
    try:
        resolve_mission(workspace, executor=args.executor, mode=args.mode)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def review(args, cwd):
    workspace = workspace_or_exit(cwd)
    plan_path = Path(args.plan) if args.plan else None
    try:
        result, _ = write_plan_review(
            workspace,
            plan_path=plan_path,
            evidence_paths=args.evidence or [],
            decision_evidence=args.decision_evidence or [],
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    append_event(workspace, "plan_review_completed", {
        "path": "plan-review.md",
        "plan": result["plan"],
        "evidence_count": len(result["evidence"]),
        "matches": len(result["matches"]),
        "does_not_match": len(result["does_not_match"]),
        "could_not_verify": len(result["could_not_verify"]),
        "human_decision_evidence": result["human_decision_evidence"],
    })
    print("Plan Review")
    print(f"- Plan: {result['plan']}")
    print(f"- Requirements reviewed: {len(result['requirements'])}")
    print(f"- Evidence files: {len(result['evidence'])}")
    print(f"- Matches: {len(result['matches'])}")
    print(f"- Does not match: {len(result['does_not_match'])}")
    print(f"- Could not verify: {len(result['could_not_verify'])}")
    print("- Human decision evidence:")
    for item in result["human_decision_evidence"]:
        reference = f" ({item['reference']})" if item.get("reference") else ""
        print(f"  - {item['label']}: {item['status']}{reference}")
    print("Artifacts:")
    print(f"- {workspace / 'plan-review.md'}")
    print(f"- {workspace / 'plan-review.json'}")


def evidence_report(args, cwd):
    workspace = workspace_or_exit(cwd)
    review_path = Path(args.review) if args.review else None
    try:
        result, _ = write_evidence_report(workspace, review_path=review_path)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    append_event(workspace, "evidence_report_completed", {
        "path": "evidence-report.md",
        "schema_version": result["schema_version"],
        "artifact_version": result["artifact_version"],
        "lifecycle_status": result["lifecycle_status"],
        "plan": result["lineage"]["plan"],
        "plan_review": result["lineage"]["plan_review"],
        "verified": result["summary"]["verified"],
        "failed": result["summary"]["failed"],
        "unable_to_verify": result["summary"]["unable_to_verify"],
        "deviations": result["summary"]["deviations"],
    })
    print("Evidence Report")
    print(f"- Plan: {result['lineage']['plan']}")
    print(f"- Plan Review: {result['lineage']['plan_review']}")
    print(f"- Lifecycle status: {result['lifecycle_status']}")
    print(f"- Verified: {result['summary']['verified']}")
    print(f"- Failed: {result['summary']['failed']}")
    print(f"- Unable to verify: {result['summary']['unable_to_verify']}")
    print(f"- Deviations: {result['summary']['deviations']}")
    print(f"- Recommendation: {result['battalion_recommendation']}")
    print("Artifacts:")
    print(f"- {workspace / 'evidence-report.md'}")
    print(f"- {workspace / 'evidence-report.json'}")


def parser():
    result = argparse.ArgumentParser(prog="battalion", description="Battalion v0.8.0 deterministic mission assessment, planning, review, evidence, dispatch, assurance, and resolve")
    commands = result.add_subparsers(dest="command", required=True)
    p = commands.add_parser("plan"); p.add_argument("--requirement", help="Add one requirement manually instead of generating a mission contract")
    p.add_argument("--acceptance", action="append", help="Acceptance criterion; repeat for multiple criteria")
    p.add_argument("--review", action="append", help="Required standing-team reviewer id; repeat for multiple reviews")
    p.add_argument("--architecture", action="append", help="Architecture reference filename to record in the mission plan; repeat for multiple references")
    p = commands.add_parser("dispatch")
    p.add_argument("--executor", help=f"Dispatch .battalion/mission-plan.md to a supported executor: {', '.join(sorted(SUPPORTED_EXECUTORS))}")
    p.add_argument("--mode", choices=["auto", "standard"], default="standard", help="Executor invocation mode; auto permits routine local implementation work but never source control or deployment actions")
    p.add_argument("--allow-implementation-before-reviews", action="store_true", help="Explicitly allow owner implementation before planning/design reviews are completed")
    p = commands.add_parser("execute")
    p.add_argument("--outcome", choices=sorted(RESULT_OUTCOMES), default="COMPLETE")
    p.add_argument("--summary")
    p.add_argument("--evidence", action="append", help="Evidence path reported by simulated execution; repeat for multiple paths")
    p.add_argument("--failure-type", choices=sorted(FAILURE_TYPES), default="OTHER")
    p.add_argument("--reason")
    p.add_argument("--impact")
    p.add_argument("--recommendation")
    p.add_argument("--decision-action", choices=sorted(DISPATCHER_ACTIONS), help="Dispatcher decision to record for non-COMPLETE simulated outcomes")
    commands.add_parser("status")
    p = commands.add_parser("assess")
    p.add_argument("requirement_text", nargs="?", help="Requirement text or path to a requirement file to assess")
    p.add_argument("--requirement", help=argparse.SUPPRESS)
    p.add_argument("--resolver", help=argparse.SUPPRESS)
    p = commands.add_parser("assure")
    p.add_argument("--run", action="store_true", help="Run deterministic local runtime validation in addition to static assurance")
    p.add_argument("--verbose", action="store_true", help="Show full assurance evidence in CLI output")
    p = commands.add_parser("resolve")
    p.add_argument("--executor", help=f"Send failed Mission Assurance findings to a supported executor: {', '.join(sorted(SUPPORTED_EXECUTORS))}")
    p.add_argument("--mode", choices=["auto", "standard"], default="standard", help="Executor invocation mode; auto permits routine local implementation work but never source control or deployment actions")
    p = commands.add_parser("review")
    p.add_argument("--plan", help="Authoritative Plan path. Defaults to .battalion/mission-plan.md.")
    p.add_argument("--evidence", action="append", help="Evidence file to compare against the Plan; repeat for multiple files.")
    p.add_argument(
        "--decision-evidence",
        action="append",
        help=(
            "Observed human decision evidence as source=status[:reference]. "
            "Sources: pr-approval, pr-merge, manual-artifact. "
            "Manual artifact updates are optional fallback evidence, not the default PR workflow."
        ),
    )
    p = commands.add_parser("evidence-report")
    p.add_argument("--review", help="Plan Review JSON path. Defaults to .battalion/plan-review.json.")
    commands.add_parser("report")
    return result


def main(argv=None, cwd=None):
    args = parser().parse_args(argv); cwd = Path.cwd() if cwd is None else Path(cwd)
    {
        "plan": plan,
        "dispatch": dispatch,
        "execute": execute,
        "status": status,
        "assess": assessment,
        "assure": assurance,
        "resolve": resolve,
        "review": review,
        "evidence-report": evidence_report,
        "report": report,
    }[args.command](args, cwd)


if __name__ == "__main__": main()
