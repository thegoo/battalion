import argparse
import json
import sys
from pathlib import Path

from .agents import standing_team
from .assessment import infer_attributes, write_assessment
from .assurance import assure
from .dispatcher import DISPATCHER_ACTIONS, FAILURE_TYPES, RESULT_OUTCOMES, dispatch_next, execute_active, runtime_status
from .mission_analyst import generate_mission_contract, reconcile_mission_contract
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
        content = render_mission_plan(read_yaml(workspace / "mission.yaml"), ledger, assessment)
        target = workspace / "mission-plan.md"
        target.write_text(content, encoding="utf-8")
        append_event(workspace, "mission_plan_created", {
            "path": str(target.relative_to(workspace.parent)),
            "assessment_schema_version": assessment.get("schema_version"),
            "readiness": assessment.get("readiness"),
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


def render_mission_plan(mission, ledger, assessment):
    requirements = ledger.get("requirements", [])
    lines = [
        "# Battalion Mission Plan",
        "",
        "## Mission",
        "",
        f"- **Title:** {mission.get('title', '—')}",
        f"- **Objective:** {mission.get('objective', '—')}",
        "",
        "## Assessment Gate",
        "",
        f"- **Readiness:** {assessment.get('readiness', '—')}",
        f"- **Recommendation:** {assessment.get('recommendation', '—')}",
        "",
        "## Readiness Reasons",
        "",
    ]
    lines.extend(f"- {reason}" for reason in assessment.get("readiness_reason", []) or ["None recorded"])
    lines.extend(["", "## Recommendation Rationale", ""])
    lines.extend(f"- {reason}" for reason in assessment.get("recommendation_reason", []) or ["None recorded"])
    lines.extend(["", "## Execution Requirements", ""])
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        lines.extend([
            f"### {requirement.get('id', '—')} — {requirement.get('statement', '—')}",
            "",
            f"- **Owner:** {requirement.get('owner', '—')}",
            f"- **Status:** {requirement.get('status', '—')}",
            "- **Acceptance Criteria:**",
        ])
        lines.extend(f"  - {item}" for item in requirement.get("acceptance", []))
        lines.append("- **Required Reviews:**")
        for review in requirement.get("required_reviews", []):
            if isinstance(review, dict):
                lines.append(f"  - {review.get('reviewer', '—')} ({review.get('status', '—')})")
        lines.append("")
    lines.extend([
        "## Clarifications",
        "",
    ])
    clarifications = ledger.get("clarifications", [])
    if clarifications:
        lines.extend(
            f"- {item.get('id', '—')} [{item.get('status', '—')}]: {item.get('question', '—')}"
            for item in clarifications if isinstance(item, dict)
        )
    else:
        lines.append("- None")
    lines.extend(["", "## Constraints", ""])
    constraints = ledger.get("constraints", {})
    if isinstance(constraints, dict) and constraints:
        for category, values in constraints.items():
            if not values:
                continue
            lines.append(f"### {str(category).title()}")
            for constraint in values:
                if isinstance(constraint, dict):
                    lines.append(f"- {constraint.get('id', '—')}: {constraint.get('statement', '—')}")
            lines.append("")
    else:
        lines.append("- None")
    lines.extend(["## Assumptions", ""])
    assumptions = ledger.get("assumptions", [])
    if assumptions:
        for assumption in assumptions:
            if isinstance(assumption, dict):
                lines.append(f"- {assumption.get('id', '—')}: {assumption.get('statement', '—')}")
            else:
                lines.append(f"- {assumption}")
    else:
        lines.append("- None")
    lines.extend(["", "## Risks", ""])
    risks = ledger.get("risks", [])
    if risks:
        for risk in risks:
            if isinstance(risk, dict):
                lines.append(f"- {risk.get('id', '—')}: {risk.get('statement', '—')}")
            else:
                lines.append(f"- {risk}")
    else:
        lines.append("- None")
    lines.extend([
        "",
        "## Next Execution Steps",
        "",
        "1. Resolve open clarifications before implementation readiness is finalized.",
        "2. Complete required planning, architecture, and security reviews.",
        "3. Dispatch runtime assignments sequentially with `battalion dispatch`.",
        "4. Attach evidence during execution and run Mission Assurance after implementation evidence exists.",
    ])
    lines.extend([
        "",
        "## Assessment Artifact",
        "",
        "- `.battalion/assessment.json`",
        "- `.battalion/assessment.md`",
        "",
    ])
    return "\n".join(lines)


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
    for item in open_items:
        print(f"\n{item['id']}\n{item['question']}\nAnswer: {item.get('answer') or 'None'}")

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
        for item in open_items:
            answer = input(f"\n{item['id']} — {item['question']}\n> ").strip()
            if answer:
                actions.append((item["id"], "resolved", answer))
        if actions and not resolver:
            resolver = input("\nResolved by: ").strip()
    elif not resolver and sys.stdin.isatty():
        resolver = input("Resolved by: ").strip()
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


def dispatch(args, cwd):
    workspace = workspace_or_exit(cwd)
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
        resolve_assessment_clarifications(workspace, args)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        result = write_assessment(workspace)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Readiness: {result['readiness']}")
    print("Readiness Reasons:")
    for reason in result.get("readiness_reason", []):
        print(f"- {reason}")
    print(f"Recommendation: {result['recommendation']}")
    print("Recommendation Rationale:")
    for reason in result.get("recommendation_reason", []):
        print(f"- {reason}")
    print(f"Assessment JSON: {workspace / 'assessment.json'}")
    print(f"Assessment Report: {workspace / 'assessment.md'}")


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


def resolve_assessment_clarifications(workspace, args):
    ledger = read_yaml(workspace / "ledger.yaml")
    clarifications = ledger.get("clarifications", [])
    if not isinstance(clarifications, list):
        return
    open_items = [item for item in clarifications if isinstance(item, dict) and item.get("status") == "open"]
    if not open_items:
        return
    if not sys.stdin.isatty():
        print("Clarifications are required before readiness can be finalized. Run battalion clarify.")
        return
    print("Clarifications are required before readiness can be finalized.")
    actions = []
    for item in open_items:
        answer = input(f"\n{item['id']} — {item['question']}\nPress Enter to skip.\n> ").strip()
        if answer:
            actions.append((item["id"], "resolved", answer))
    if not actions:
        print("\nNo clarification answers provided; readiness will remain NOT_READY.")
        return
    resolver = args.resolver or input("\nResolved by: ").strip()
    if not resolver:
        raise SystemExit("Provide --resolver for clarification actions.")
    apply_clarification_actions(workspace, ledger, actions, resolver)
    print(f"\nResolved {len(actions)} clarification(s) during assessment.")


def assurance(args, cwd):
    workspace = workspace_or_exit(cwd)
    result = assure(workspace)
    if (workspace / "events.jsonl").is_file(): append_event(workspace, "assurance_completed", result.to_dict())
    counts = result.clarification_counts
    print(
        f"Status: {result.status}\nRecommendation: {result.recommendation}\nConfidence: {result.confidence}\n"
        f"Clarifications: {counts.get('open', 0)} open, {counts.get('resolved', 0)} resolved, "
        f"{counts.get('superseded', 0)} superseded, {counts.get('rejected', 0)} rejected\nFindings:"
    )
    for finding in result.findings: print(f"- {finding}")


def report(args, cwd):
    workspace = workspace_or_exit(cwd)
    try: content = render_report(workspace)
    except ValueError as exc: raise SystemExit(str(exc)) from exc
    target = workspace / "reports" / "mission-report.md"; target.parent.mkdir(exist_ok=True); target.write_text(content, encoding="utf-8")
    append_event(workspace, "report_generated", {"path": str(target.relative_to(cwd))})
    print(f"Generated {target}")


def parser():
    result = argparse.ArgumentParser(prog="battalion", description="Battalion v0.3.2 init-assess-plan workflow")
    commands = result.add_subparsers(dest="command", required=True)
    p = commands.add_parser("init"); p.add_argument("--title"); p.add_argument("--objective"); p.add_argument("--prompt")
    p = commands.add_parser("plan"); p.add_argument("--requirement", help="Add one requirement manually instead of generating a mission contract")
    p.add_argument("--acceptance", action="append", help="Acceptance criterion; repeat for multiple criteria")
    p.add_argument("--review", action="append", help="Required standing-team reviewer id; repeat for multiple reviews")
    p = commands.add_parser("clarify")
    p.add_argument("--resolver", help="Human responsible for the clarification decision")
    p.add_argument("--answer", action="append", metavar="Q-ID=VALUE", help="Resolve a clarification; repeat as needed")
    p.add_argument("--reject", action="append", metavar="Q-ID=REASON", help="Reject a clarification; repeat as needed")
    p.add_argument("--supersede", action="append", metavar="Q-ID=VALUE", help="Supersede a clarification; repeat as needed")
    p = commands.add_parser("dispatch")
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
    p.add_argument("--resolver", help="Human responsible for clarification answers collected during assessment")
    commands.add_parser("assure"); commands.add_parser("report")
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
        "report": report,
    }[args.command](args, cwd)


if __name__ == "__main__": main()
