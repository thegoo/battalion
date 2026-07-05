import argparse
import json
import re
import sys
from pathlib import Path

from .agents import standing_team
from .assessment import infer_attributes, write_assessment
from .assurance import assure
from .classification import write_default_attribute_catalog
from .dispatcher import DISPATCHER_ACTIONS, FAILURE_TYPES, RESULT_OUTCOMES, dispatch_next, execute_active, runtime_status
from .executor_dispatch import SUPPORTED_EXECUTORS, dispatch_engineering_brief
from .mission_analyst import generate_mission_contract, reconcile_mission_contract
from .mission_resolve import resolve_mission
from .reporting import render_report
from .storage import append_event, read_yaml, root, timestamp, write_yaml


DOCTRINE = ["mission_first", "evidence_over_assertion", "requirement_traceability", "zero_trust", "adversarial_review", "separation_of_duties", "human_authority", "audit_everything_material"]
NO_MISSION_MESSAGE = """Current directory does not contain a Battalion mission.

Run:

  battalion init

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


def plan(args, cwd):
    workspace = workspace_or_exit(cwd)
    statement = args.requirement
    ledger = read_yaml(workspace / "ledger.yaml")
    if not statement:
        assessment_path = workspace / "assessment.json"
        if not assessment_path.is_file():
            raise SystemExit("No mission assessment exists. Run battalion assess first.")
        assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
        readiness = assessment.get("readiness")
        if readiness not in {"READY", "READY_WITH_RISK"}:
            raise SystemExit(f"Mission planning requires assessment readiness READY or READY_WITH_RISK. Current readiness: {readiness or 'UNKNOWN'}.")
        content = render_mission_plan(read_yaml(workspace / "mission.yaml"), ledger, assessment, args.architecture or [])
        target = workspace / "mission-plan.md"
        target.write_text(content, encoding="utf-8")
        append_event(workspace, "mission_plan_created", {
            "path": str(target.relative_to(workspace.parent)),
            "assessment_schema_version": assessment.get("schema_version"),
            "readiness": assessment.get("readiness"),
            "architecture_references": args.architecture or [],
        })
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


def render_mission_plan(mission, ledger, assessment, architecture_references=None):
    architecture_references = architecture_references or []
    requirements = [item for item in ledger.get("requirements", []) if isinstance(item, dict)]
    constraints = ledger.get("constraints", {}) if isinstance(ledger.get("constraints"), dict) else {}
    resolved_clarifications = [
        item for item in ledger.get("clarifications", [])
        if isinstance(item, dict) and item.get("status") in {"resolved", "superseded"}
    ]
    lines = [
        "# Mission",
        "",
        f"**Title:** {mission.get('title', '—')}",
        "",
        "## Background",
        "",
        _mission_background(mission, ledger, constraints),
        "",
        "## Mission Objective",
        "",
        mission.get("objective") or mission.get("mission_prompt") or "No mission objective was identified during assessment.",
        "",
        "## Business Outcome",
        "",
        _business_outcome(mission, ledger, constraints),
        "",
        "## Readiness Summary",
        "",
    ]
    lines.extend(_readiness_summary_lines(assessment))
    lines.extend([
        "",
        "## Mission Classification",
        "",
    ])
    lines.append("Detected mission attributes:")
    lines.append("")
    lines.extend(_bullet(assessment.get("mission_attributes"), "No mission attributes were identified during assessment."))
    lines.extend([
        "",
        "## Functional Requirements",
        "",
    ])
    lines.extend(_requirement_lines(requirements, constraints))
    lines.extend([
        "",
        "## Non-Functional Requirements",
        "",
    ])
    lines.extend(_non_functional_lines(requirements, constraints))
    lines.extend([
        "",
        "## Engineering Constraints",
        "",
    ])
    lines.extend(_constraint_lines(constraints, resolved_clarifications))
    lines.extend([
        "",
        "## Architecture References",
        "",
    ])
    if architecture_references:
        lines.append("The following engineering references have been identified for this mission:")
        lines.append("")
        lines.extend(f"- {name}" for name in architecture_references)
        lines.extend([
            "",
            "Implementation shall conform to these engineering references.",
            "Planning did not inspect, validate, summarize, or interpret their contents.",
        ])
    else:
        lines.append("No architecture reference filenames were supplied for this mission.")
    lines.extend([
        "",
        "## Assumptions",
        "",
    ])
    lines.append("The following assumptions remain part of the implementation context:")
    lines.append("")
    lines.extend(_contract_item_lines(ledger.get("assumptions"), "No assumptions were identified during assessment."))
    lines.extend([
        "",
        "## Risks",
        "",
    ])
    lines.append("The following risks should be reviewed during implementation and assurance:")
    lines.append("")
    lines.extend(_risk_lines(assessment))
    lines.extend([
        "",
        "## Implementation Guidance",
        "",
    ])
    lines.extend(_implementation_guidance(mission, requirements, constraints, architecture_references))
    lines.extend([
        "",
        "## Suggested Work Breakdown",
        "",
    ])
    lines.extend(_work_breakdown(requirements, constraints))
    lines.extend([
        "",
        "## Testing Strategy",
        "",
    ])
    lines.extend(_testing_strategy(requirements, constraints))
    lines.extend([
        "",
        "## Evidence Required",
        "",
    ])
    lines.extend(_evidence_required(requirements, constraints))
    lines.extend([
        "",
        "## Definition of Done",
        "",
        "- Acceptance criteria for every requirement are satisfied.",
        "- Required evidence has been produced and attached to the mission record.",
        "- Engineering constraints identified during assessment are satisfied.",
        "- Required architecture references have been reviewed when filenames were supplied.",
        "- Required deliverables from the assessed mission are complete.",
        "",
        "## Out of Scope",
        "",
        "- Planning does not dispatch work.",
        "- Planning does not execute work.",
        "- Planning does not invoke AI.",
        "- Planning does not inspect architecture documents.",
        "- No additional out-of-scope items were identified during assessment.",
        "",
        "## Mission Success Criteria",
        "",
    ])
    lines.extend(_success_criteria(mission, requirements, constraints))
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
    if constraints.get("functional") and _has_text(text, r"health"):
        return "Operators gain a simple, automatable signal for service health, enabling faster validation of whether the service is running and responding as expected."
    if constraints.get("functional") and _has_text(text, r"\bapi\b|endpoint|http"):
        return "Consumers gain a predictable API behavior that can be implemented, tested, and validated against the mission acceptance criteria."
    if _has_text(text, r"\bcli\b|command[- ]line"):
        return "Users gain a local command-line utility that performs the requested behavior with documented validation evidence."
    return "No explicit business or operational outcome was identified during assessment."


def _bullet(values, empty):
    values = values or []
    return [f"- {value}" for value in values] if values else [f"- {empty}"]


def _readiness_summary_lines(assessment):
    assumptions = assessment.get("assumptions") or []
    open_risks = assessment.get("risks") or []
    resolved_risks = assessment.get("resolved_risks") or []
    lines = [
        f"- **Readiness:** {assessment.get('readiness', '—')}",
        f"- **Recommendation:** {assessment.get('recommendation', '—')}",
        f"- **Assumptions:** {len(assumptions)} documented",
        f"- **Open risks:** {len(open_risks)} documented",
    ]
    if resolved_risks:
        lines.append(f"- **Resolved risks:** {len(resolved_risks)} dispositioned")
    reasons = assessment.get("recommendation_reason") or assessment.get("readiness_reason") or []
    if reasons:
        lines.append(f"- **Planning note:** {reasons[0]}")
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
    if constraints.get("functional"):
        return "The implementation shall deliver the functional behavior captured by the assessed mission contract."
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
    if constraints.get("functional") and _has_text(text, r"health"):
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


def _evidence_required(requirements, constraints):
    lines = ["- Evidence that every acceptance criterion has been satisfied."]
    if constraints.get("testing"):
        lines.append("- Passing automated test output.")
    if constraints.get("technical"):
        lines.append("- Successful build or execution evidence for the specified technology stack.")
    if constraints.get("operational"):
        lines.append("- Operational validation evidence for startup, runtime, or deployment expectations.")
    if any("docker" in item.get("statement", "").lower() or "container" in item.get("statement", "").lower() for item in constraints.get("technical", []) + constraints.get("operational", []) if isinstance(item, dict)):
        lines.append("- Container build and run evidence.")
    lines.append("- Review evidence for required reviews recorded on mission requirements.")
    return lines


def _success_criteria(mission, requirements, constraints):
    if not requirements:
        return ["- No mission success criteria could be derived because no requirements were identified during assessment."]
    text = _mission_text(mission, {"mission_prompt": ""})
    lines = []
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
    workspace = workspace_or_exit(cwd)
    try:
        ensure_assessed_contract(workspace)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        result = write_assessment(workspace)
        if args.interactive:
            if resolve_assessment_clarifications(workspace, args, result):
                result = write_assessment(workspace)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print_assessment_summary(result)
    print(f"Assessment JSON: {workspace / 'assessment.json'}")
    print(f"Assessment Report: {workspace / 'assessment.md'}")


def print_assessment_summary(result):
    print(f"Readiness: {result['readiness']}")
    print(f"\nEngineering Compatibility Disclaimer\n- {result['engineering_compatibility_disclaimer']}")
    print("\nMission Classification")
    attributes = result.get("mission_classification", {}).get("attributes", [])
    if not attributes:
        print("- None")
    for item in attributes:
        evidence = ", ".join(
            f"{entry.get('indicator', '—')} from {entry.get('source', '—')}"
            for entry in item.get("classification_evidence", [])
        ) or "None"
        print(f"- {item.get('attribute', '—')}: {item.get('decision', 'not_classified')}; evidence [{evidence}]; hit count {item.get('hit_count', 0)}; threshold {item.get('threshold', 1)}")
    print("\nPrimary Findings")
    for finding in primary_assessment_findings(result):
        print(f"- {finding}")
    print("\nOutstanding Clarifications")
    clarifications = result.get("outstanding_clarifications", [])
    if clarifications:
        for item in clarifications:
            print(f"- {item.get('id', '—')}: {item.get('question', '—')}")
    else:
        print("- None")
    print(f"\nRecommendation: {result['recommendation']}")
    for reason in result.get("recommendation_reason", []):
        print(f"- {reason}")
    if clarifications:
        print("\nRun:\n  battalion clarify")


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
    contract = generate_mission_contract(mission["id"], mission_prompt, timestamp())
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


def resolve_assessment_clarifications(workspace, args, assessment_result):
    ledger = read_yaml(workspace / "ledger.yaml")
    clarifications = ledger.get("clarifications", [])
    if not isinstance(clarifications, list):
        return False
    open_items = [item for item in clarifications if isinstance(item, dict) and item.get("status") == "open"]
    if not open_items:
        return False
    if not sys.stdin.isatty():
        raise SystemExit("Interactive assessment requires a terminal. Run battalion clarify or use --answer with battalion clarify.")
    print_assessment_summary(assessment_result)
    print("\nInteractive assessment clarification resolution")
    print_open_clarifications(open_items)
    actions = collect_clarification_actions(open_items)
    if not actions:
        print("\nNo clarification answers provided; readiness will remain NOT_READY.")
        return False
    resolver = args.resolver or prompt_user("\nResolved by: ").strip()
    if not resolver:
        raise SystemExit("Provide --resolver for clarification actions.")
    apply_clarification_actions(workspace, ledger, actions, resolver)
    print(f"\nResolved {len(actions)} clarification(s) during assessment.")
    print("Re-running assessment after clarification updates.\n")
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


def parser():
    result = argparse.ArgumentParser(prog="battalion", description="Battalion v0.7.0 deterministic mission assessment, planning, dispatch, assurance, and resolve")
    commands = result.add_subparsers(dest="command", required=True)
    p = commands.add_parser("init"); p.add_argument("--title"); p.add_argument("--objective"); p.add_argument("--prompt")
    p = commands.add_parser("plan"); p.add_argument("--requirement", help="Add one requirement manually instead of generating a mission contract")
    p.add_argument("--acceptance", action="append", help="Acceptance criterion; repeat for multiple criteria")
    p.add_argument("--review", action="append", help="Required standing-team reviewer id; repeat for multiple reviews")
    p.add_argument("--architecture", action="append", help="Architecture reference filename to record in the mission plan; repeat for multiple references")
    p = commands.add_parser("clarify")
    p.add_argument("--resolver", help="Human responsible for the clarification decision")
    p.add_argument("--answer", action="append", metavar="Q-ID=VALUE", help="Resolve a clarification; repeat as needed")
    p.add_argument("--reject", action="append", metavar="Q-ID=REASON", help="Reject a clarification; repeat as needed")
    p.add_argument("--supersede", action="append", metavar="Q-ID=VALUE", help="Supersede a clarification; repeat as needed")
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
    p.add_argument("--interactive", action="store_true", help="Prompt for outstanding clarification answers during assessment")
    p.add_argument("--resolver", help="Human responsible for clarification answers collected during assessment")
    p = commands.add_parser("assure")
    p.add_argument("--run", action="store_true", help="Run deterministic local runtime validation in addition to static assurance")
    p.add_argument("--verbose", action="store_true", help="Show full assurance evidence in CLI output")
    p = commands.add_parser("resolve")
    p.add_argument("--executor", help=f"Send failed Mission Assurance findings to a supported executor: {', '.join(sorted(SUPPORTED_EXECUTORS))}")
    p.add_argument("--mode", choices=["auto", "standard"], default="standard", help="Executor invocation mode; auto permits routine local implementation work but never source control or deployment actions")
    commands.add_parser("report")
    return result


def main(argv=None, cwd=None):
    args = parser().parse_args(argv); cwd = Path.cwd() if cwd is None else Path(cwd)
    {
        "init": init,
        "plan": plan,
        "clarify": clarify,
        "dispatch": dispatch,
        "execute": execute,
        "status": status,
        "assess": assessment,
        "assure": assurance,
        "resolve": resolve,
        "report": report,
    }[args.command](args, cwd)


if __name__ == "__main__": main()
