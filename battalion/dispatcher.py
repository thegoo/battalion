from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import append_event, read_yaml, timestamp, write_yaml


ASSIGNMENT_STATES = {"CREATED", "ASSIGNED", "EXECUTING", "WAITING", "COMPLETE", "BLOCKED", "FAILED", "ABORTED", "CLOSED"}
ACTIVE_ASSIGNMENT_STATES = {"CREATED", "ASSIGNED", "EXECUTING", "WAITING", "BLOCKED"}
RESULT_OUTCOMES = {"COMPLETE", "BLOCKED", "FAILED", "NEEDS_CLARIFICATION", "NEEDS_SUPPORT", "ABORTED"}
DISPATCHER_ACTIONS = {
    "retry_assignment",
    "return_work_to_previous_unit",
    "request_supporting_unit",
    "generate_clarification",
    "escalate_to_human",
    "accept_risk",
    "abort_mission",
}
FAILURE_TYPES = {
    "MISSING_CONTEXT",
    "DEPENDENCY_MISSING",
    "VALIDATION_FAILED",
    "SECURITY_BLOCKER",
    "TOOL_FAILURE",
    "PERMISSION_DENIED",
    "UNRECOVERABLE_ERROR",
    "OTHER",
}


def assignment_path(workspace: Path) -> Path:
    return workspace / "assignments.yaml"


def load_assignments(workspace: Path) -> Dict[str, Any]:
    path = assignment_path(workspace)
    if not path.exists():
        return {"assignments": []}
    value = read_yaml(path)
    if not isinstance(value, dict) or not isinstance(value.get("assignments"), list):
        raise ValueError("assignments.yaml must contain an assignments list")
    return value


def save_assignments(workspace: Path, runtime: Dict[str, Any]) -> None:
    write_yaml(assignment_path(workspace), runtime)


def _history(action: str, status: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"timestamp": timestamp(), "actor": "dispatcher", "action": action, "status": status, "details": details or {}}


def _assignment_id(assignments: List[Dict[str, Any]]) -> str:
    return f"ASG-{len(assignments) + 1:03d}"


def _team_by_id(workspace: Path) -> Dict[str, Dict[str, Any]]:
    agents = read_yaml(workspace / "agents.yaml").get("agents", [])
    return {agent["id"]: agent for agent in agents if isinstance(agent, dict) and agent.get("id")}


def _closed_requirement(requirement: Dict[str, Any]) -> bool:
    return requirement.get("status") in {"completed", "deferred", "rejected", "accepted_risk"}


def _active_assignment(assignments: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return next((item for item in assignments if item.get("status") in ACTIVE_ASSIGNMENT_STATES and item.get("ownership") != "released"), None)


def _requirement_by_id(ledger: Dict[str, Any], requirement_id: str) -> Optional[Dict[str, Any]]:
    return next((item for item in ledger.get("requirements", []) if item.get("id") == requirement_id), None)


def _completed_assignment(assignments: List[Dict[str, Any]], requirement_id: str, assignment_type: str, assigned_unit: Optional[str] = None) -> bool:
    return any(
        item.get("requirement_id") == requirement_id
        and item.get("assignment_type") == assignment_type
        and item.get("status") == "COMPLETE"
        and (assigned_unit is None or item.get("assigned_unit") == assigned_unit)
        for item in assignments
    )


def _implementation_evidence(requirement: Dict[str, Any], assignments: List[Dict[str, Any]]) -> List[str]:
    evidence = list(requirement.get("evidence") or [])
    for assignment in assignments:
        if (
            assignment.get("requirement_id") == requirement.get("id")
            and assignment.get("assignment_type") == "implementation"
            and assignment.get("status") == "COMPLETE"
        ):
            evidence.extend(assignment.get("evidence") or [])
    return [item for item in evidence if isinstance(item, str) and item.strip()]


def _pending_review(requirement: Dict[str, Any], reviewer: str) -> Optional[Dict[str, Any]]:
    return next(
        (
            review for review in requirement.get("required_reviews", [])
            if isinstance(review, dict)
            and review.get("reviewer") == reviewer
            and review.get("status") == "pending"
        ),
        None,
    )


def _pending_reviews(requirement: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        review for review in requirement.get("required_reviews", [])
        if isinstance(review, dict) and review.get("status") == "pending"
    ]


def _relevant_constraints(ledger: Dict[str, Any], requirement: Dict[str, Any]) -> List[Dict[str, Any]]:
    linked = set(requirement.get("traceability", {}).get("constraint_ids", []))
    if not linked:
        return []
    return [
        constraint
        for values in ledger.get("constraints", {}).values()
        for constraint in values
        if isinstance(constraint, dict) and constraint.get("id") in linked
    ]


def _resolved_clarifications(ledger: Dict[str, Any], requirement: Dict[str, Any]) -> List[Dict[str, Any]]:
    linked = set(requirement.get("traceability", {}).get("clarification_ids", []))
    return [
        clarification
        for clarification in ledger.get("clarifications", [])
        if isinstance(clarification, dict)
        and clarification.get("status") in {"resolved", "superseded"}
        and (not linked or clarification.get("id") in linked)
    ]


def _required_outputs(unit: Dict[str, Any], requirement: Dict[str, Any], assignment_type: str) -> List[str]:
    outputs = list(unit.get("required_outputs", []))
    if assignment_type == "implementation" and "evidence references" not in outputs:
        outputs.append("evidence references")
    if assignment_type == "review" and "review evidence" not in outputs:
        outputs.append("review evidence")
    return outputs


def scoped_context(workspace: Path, requirement: Dict[str, Any], assigned_unit: str, assignment_type: str, review: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ledger = read_yaml(workspace / "ledger.yaml")
    if assigned_unit in {"dispatcher", "mission_assurance"}:
        return {"mission_contract": ledger}
    context = {
        "assignment_type": assignment_type,
        "requirement": {
            "id": requirement.get("id"),
            "statement": requirement.get("statement"),
            "status": requirement.get("status"),
            "owner": requirement.get("owner"),
            "acceptance": requirement.get("acceptance", []),
            "required_reviews": requirement.get("required_reviews", []),
            "traceability": requirement.get("traceability", {}),
        },
        "relevant_constraints": _relevant_constraints(ledger, requirement),
        "resolved_clarifications": _resolved_clarifications(ledger, requirement),
        "required_evidence": requirement.get("evidence", []),
    }
    if review is not None:
        context["review"] = {
            "reviewer": review.get("reviewer"),
            "status": review.get("status"),
            "reason": review.get("reason", ""),
        }
    return context


def _create_assignment(
    workspace: Path,
    runtime: Dict[str, Any],
    requirement: Dict[str, Any],
    assigned_unit: str,
    assignment_type: str,
    review: Optional[Dict[str, Any]] = None,
    dependencies: Optional[List[str]] = None,
) -> Dict[str, Any]:
    team = _team_by_id(workspace)
    if assigned_unit not in team:
        assigned_unit = "developer"
    assignment = {
        "id": _assignment_id(runtime["assignments"]),
        "requirement_id": requirement["id"],
        "assigned_unit": assigned_unit,
        "assignment_type": assignment_type,
        "reviewer": review.get("reviewer") if review else None,
        "ownership": "owned",
        "status": "ASSIGNED",
        "scoped_context": scoped_context(workspace, requirement, assigned_unit, assignment_type, review),
        "required_outputs": _required_outputs(team.get(assigned_unit, {}), requirement, assignment_type),
        "dependencies": dependencies or [],
        "evidence": [],
        "result_packet": None,
        "abort_packet": None,
        "audit_history": [
            _history("CREATED", "CREATED", {"requirement_id": requirement["id"]}),
            _history("ASSIGNED", "ASSIGNED", {"assigned_unit": assigned_unit}),
        ],
    }
    runtime["assignments"].append(assignment)
    append_event(workspace, "assignment_created", {
        "assignment_id": assignment["id"],
        "requirement_id": requirement["id"],
        "assigned_unit": assigned_unit,
        "assignment_type": assignment_type,
        "reviewer": assignment["reviewer"],
    }, actor="dispatcher")
    append_event(workspace, "assignment_state_changed", {
        "assignment_id": assignment["id"],
        "from": "CREATED",
        "to": "ASSIGNED",
    }, actor="dispatcher")
    return assignment


def _next_assignment_spec(
    requirements: List[Dict[str, Any]],
    assignments: List[Dict[str, Any]],
    allow_implementation_before_reviews: bool,
) -> Optional[Dict[str, Any]]:
    for requirement in requirements:
        if not isinstance(requirement, dict) or _closed_requirement(requirement):
            continue
        requirement_id = requirement.get("id")
        if not isinstance(requirement_id, str):
            continue
        architect_review = _pending_review(requirement, "architect")
        if architect_review and not allow_implementation_before_reviews:
            return {
                "requirement": requirement,
                "assigned_unit": "architect",
                "assignment_type": "review",
                "review": architect_review,
                "dependencies": [],
            }
        owner = requirement.get("owner") or "developer"
        implementation_done = _completed_assignment(assignments, requirement_id, "implementation", owner) or bool(_implementation_evidence(requirement, assignments))
        if not implementation_done:
            return {
                "requirement": requirement,
                "assigned_unit": owner,
                "assignment_type": "implementation",
                "review": None,
                "dependencies": [],
            }
        implementation_evidence = _implementation_evidence(requirement, assignments)
        for review in _pending_reviews(requirement):
            reviewer = review.get("reviewer")
            if reviewer == "architect":
                continue
            if reviewer == "tester" and not implementation_evidence:
                continue
            return {
                "requirement": requirement,
                "assigned_unit": reviewer,
                "assignment_type": "review",
                "review": review,
                "dependencies": [assignment["id"] for assignment in assignments if assignment.get("requirement_id") == requirement_id and assignment.get("assignment_type") == "implementation"],
            }
        if implementation_evidence and not _pending_reviews(requirement):
            requirement["status"] = "completed"
    return None


def dispatch_next(workspace: Path, allow_implementation_before_reviews: bool = False) -> Dict[str, Any]:
    ledger = read_yaml(workspace / "ledger.yaml")
    runtime = load_assignments(workspace)
    active = _active_assignment(runtime["assignments"])
    if active:
        append_event(workspace, "dispatcher_decision", {
            "action": "continue_active_assignment",
            "assignment_id": active["id"],
            "recommendation": "Execute or resolve the active assignment before dispatching more work.",
        }, actor="dispatcher")
        return {"assignment": active, "decision": "continue_active_assignment", "created": False}
    blocker = next((item for item in runtime["assignments"] if item.get("status") in {"FAILED"} and item.get("ownership") != "released"), None)
    if blocker:
        append_event(workspace, "dispatcher_decision", {
            "action": "halt_for_blocker",
            "assignment_id": blocker["id"],
            "recommendation": (blocker.get("abort_packet") or {}).get("recommendation") or "Resolve blocked work before dispatching more assignments.",
        }, actor="dispatcher")
        return {"assignment": blocker, "decision": "halt_for_blocker", "created": False}

    spec = _next_assignment_spec(ledger.get("requirements", []), runtime["assignments"], allow_implementation_before_reviews)
    if spec is None:
        write_yaml(workspace / "ledger.yaml", ledger)
        append_event(workspace, "dispatcher_decision", {
            "action": "no_dispatchable_work",
            "recommendation": "No open requirement is available for dispatch.",
        }, actor="dispatcher")
        save_assignments(workspace, runtime)
        return {"assignment": None, "decision": "no_dispatchable_work", "created": False}

    requirement = spec["requirement"]
    requirement["status"] = "in_progress"
    assignment = _create_assignment(
        workspace,
        runtime,
        requirement,
        spec["assigned_unit"],
        spec["assignment_type"],
        spec["review"],
        spec["dependencies"],
    )
    write_yaml(workspace / "ledger.yaml", ledger)
    save_assignments(workspace, runtime)
    append_event(workspace, "dispatcher_decision", {
        "action": "assign_requirement",
        "assignment_id": assignment["id"],
        "requirement_id": requirement["id"],
        "assigned_unit": assignment["assigned_unit"],
        "assignment_type": assignment["assignment_type"],
        "reviewer": assignment["reviewer"],
    }, actor="dispatcher")
    return {"assignment": assignment, "decision": "assign_requirement", "created": True}


def _transition(workspace: Path, assignment: Dict[str, Any], status: str, details: Optional[Dict[str, Any]] = None) -> None:
    if status not in ASSIGNMENT_STATES:
        raise ValueError(f"invalid assignment status: {status}")
    previous = assignment.get("status")
    assignment["status"] = status
    assignment.setdefault("audit_history", []).append(_history(status, status, details))
    append_event(workspace, "assignment_state_changed", {
        "assignment_id": assignment["id"],
        "from": previous,
        "to": status,
        "details": details or {},
    }, actor="dispatcher")
    event_type = {
        "EXECUTING": "assignment_started" if previous not in {"BLOCKED", "WAITING"} else "assignment_resumed",
        "WAITING": "assignment_waiting",
        "BLOCKED": "assignment_blocked",
        "COMPLETE": "assignment_completed",
        "FAILED": "assignment_failed",
        "ABORTED": "assignment_aborted",
    }.get(status)
    if event_type:
        append_event(workspace, event_type, {
            "assignment_id": assignment["id"],
            "requirement_id": assignment.get("requirement_id"),
            "assigned_unit": assignment.get("assigned_unit"),
            "from": previous,
            "to": status,
            "details": details or {},
        }, actor="dispatcher")


def _merge_evidence(existing: List[str], incoming: List[str]) -> List[str]:
    merged = []
    for value in list(existing or []) + list(incoming or []):
        if isinstance(value, str) and value.strip() and value not in merged:
            merged.append(value)
    return merged


def result_packet(assignment: Dict[str, Any], outcome: str, summary: str, evidence: Optional[List[str]] = None) -> Dict[str, Any]:
    if outcome not in RESULT_OUTCOMES:
        raise ValueError(f"invalid result outcome: {outcome}")
    return {
        "assignment_id": assignment["id"],
        "requirement_id": assignment["requirement_id"],
        "assigned_unit": assignment["assigned_unit"],
        "outcome": outcome,
        "summary": summary,
        "evidence": evidence or [],
        "reported_at": timestamp(),
    }


def abort_packet(assignment: Dict[str, Any], failure_type: str, reason: str, impact: str, evidence: Optional[List[str]], recommendation: str) -> Dict[str, Any]:
    if failure_type not in FAILURE_TYPES:
        raise ValueError(f"invalid failure type: {failure_type}")
    return {
        "assignment_id": assignment["id"],
        "failure_type": failure_type,
        "reason": reason,
        "impact": impact,
        "evidence": evidence or [],
        "recommendation": recommendation,
        "created_at": timestamp(),
    }


def consume_result_packet(
    workspace: Path,
    packet: Dict[str, Any],
    failure_type: str = "OTHER",
    reason: str = "",
    impact: str = "",
    recommendation: str = "",
    decision_action: Optional[str] = None,
) -> Dict[str, Any]:
    runtime = load_assignments(workspace)
    assignment = next((item for item in runtime["assignments"] if item.get("id") == packet.get("assignment_id")), None)
    if assignment is None:
        raise ValueError(f"unknown assignment: {packet.get('assignment_id')}")
    if assignment.get("status") not in ACTIVE_ASSIGNMENT_STATES:
        raise ValueError(f"{assignment['id']} is not active")
    if decision_action is not None and decision_action not in DISPATCHER_ACTIONS:
        raise ValueError(f"invalid dispatcher action: {decision_action}")

    retrying_existing_assignment = assignment.get("status") in {"BLOCKED", "WAITING"}
    if assignment.get("status") == "BLOCKED":
        _transition(workspace, assignment, "WAITING", {"reason": "retry requested"})
    if assignment.get("status") == "WAITING":
        _transition(workspace, assignment, "EXECUTING", {"outcome": packet["outcome"], "resumed": True})
    else:
        _transition(workspace, assignment, "EXECUTING", {"outcome": packet["outcome"]})
    assignment["result_packet"] = packet
    assignment["evidence"] = _merge_evidence(assignment.get("evidence", []), packet.get("evidence", []))
    append_event(workspace, "result_packet_received", packet, actor=assignment["assigned_unit"])

    ledger = read_yaml(workspace / "ledger.yaml")
    requirement = _requirement_by_id(ledger, assignment["requirement_id"])
    decision: Dict[str, Any]
    if packet["outcome"] == "COMPLETE":
        if not packet.get("evidence"):
            packet["outcome"] = "BLOCKED"
            packet["summary"] = "Dispatcher blocked COMPLETE because evidence is required."
            assignment["result_packet"] = packet
            assignment["abort_packet"] = abort_packet(
                assignment,
                "MISSING_CONTEXT",
                "COMPLETE result packet did not include evidence.",
                "Dispatcher cannot advance the requirement lifecycle without evidence.",
                [],
                "Provide evidence and retry the assignment.",
            )
            _transition(workspace, assignment, "BLOCKED", assignment["abort_packet"])
            if requirement is not None:
                requirement["status"] = "in_progress"
            decision = {
                "action": "retry_assignment",
                "assignment_id": assignment["id"],
                "recommendation": "Provide evidence and retry the assignment.",
            }
            write_yaml(workspace / "ledger.yaml", ledger)
            save_assignments(workspace, runtime)
            append_event(workspace, "dispatcher_decision", decision, actor="dispatcher")
            return {"assignment": assignment, "decision": decision, "next_assignment": None}
        _transition(workspace, assignment, "COMPLETE", {"summary": packet.get("summary")})
        assignment["ownership"] = "released"
        assignment["closed_at"] = timestamp()
        assignment["abort_packet"] = None
        if requirement is not None:
            if assignment.get("assignment_type") == "review":
                for review in requirement.get("required_reviews", []):
                    if isinstance(review, dict) and review.get("reviewer") == assignment.get("reviewer"):
                        review["status"] = "completed"
                        review["evidence"] = packet["evidence"]
                        break
            elif assignment.get("assignment_type") == "implementation":
                requirement["evidence"] = _merge_evidence(requirement.get("evidence", []), assignment.get("evidence", []))
            if _implementation_evidence(requirement, runtime["assignments"]) and not _pending_reviews(requirement):
                requirement["status"] = "completed"
            else:
                requirement["status"] = "in_progress"
        decision = {
            "action": "complete_assignment" if retrying_existing_assignment else "dispatch_next_assignment",
            "assignment_id": assignment["id"],
            "recommendation": "Assignment completed. Run battalion dispatch to assign the next requirement." if retrying_existing_assignment else "Dispatch the next open requirement.",
        }
    elif packet["outcome"] == "BLOCKED":
        _transition(workspace, assignment, "BLOCKED", {"summary": packet.get("summary")})
        if requirement is not None:
            requirement["status"] = "in_progress"
        decision = {
            "action": decision_action or "escalate_to_human",
            "assignment_id": assignment["id"],
            "recommendation": recommendation or "Resolve the blocker before continuing.",
        }
    elif packet["outcome"] == "NEEDS_CLARIFICATION":
        _transition(workspace, assignment, "WAITING", {"summary": packet.get("summary")})
        decision = {
            "action": decision_action or "generate_clarification",
            "assignment_id": assignment["id"],
            "recommendation": recommendation or "Generate or resolve a clarification before continuing.",
        }
    elif packet["outcome"] == "NEEDS_SUPPORT":
        _transition(workspace, assignment, "WAITING", {"summary": packet.get("summary")})
        decision = {
            "action": decision_action or "request_supporting_unit",
            "assignment_id": assignment["id"],
            "recommendation": recommendation or "Request a supporting unit before continuing.",
        }
    elif packet["outcome"] == "ABORTED":
        assignment["abort_packet"] = abort_packet(
            assignment, failure_type, reason or packet.get("summary", "Assignment aborted."),
            impact or "Mission execution stopped.", packet.get("evidence", []),
            recommendation or "Escalate to a human mission owner.",
        )
        _transition(workspace, assignment, "ABORTED", assignment["abort_packet"])
        assignment["ownership"] = "released"
        assignment["closed_at"] = timestamp()
        decision = {
            "action": decision_action or "abort_mission",
            "assignment_id": assignment["id"],
            "recommendation": assignment["abort_packet"]["recommendation"],
        }
    else:
        assignment["abort_packet"] = abort_packet(
            assignment, failure_type, reason or packet.get("summary", "Assignment failed."),
            impact or "Dispatcher cannot continue sequential execution.", packet.get("evidence", []),
            recommendation or "Inspect the failure and decide whether to retry, reassign, or abort.",
        )
        _transition(workspace, assignment, "FAILED", assignment["abort_packet"])
        decision = {
            "action": decision_action or "escalate_to_human",
            "assignment_id": assignment["id"],
            "recommendation": assignment["abort_packet"]["recommendation"],
        }

    write_yaml(workspace / "ledger.yaml", ledger)
    save_assignments(workspace, runtime)
    append_event(workspace, "dispatcher_decision", decision, actor="dispatcher")

    next_assignment = None
    if packet["outcome"] == "COMPLETE" and not retrying_existing_assignment:
        next_assignment = dispatch_next(workspace).get("assignment")
    return {"assignment": assignment, "decision": decision, "next_assignment": next_assignment}


def execute_active(
    workspace: Path,
    outcome: str = "COMPLETE",
    summary: Optional[str] = None,
    evidence: Optional[List[str]] = None,
    failure_type: str = "OTHER",
    reason: str = "",
    impact: str = "",
    recommendation: str = "",
    decision_action: Optional[str] = None,
) -> Dict[str, Any]:
    runtime = load_assignments(workspace)
    assignment = _active_assignment(runtime["assignments"])
    if assignment is None:
        raise ValueError("No active assignment exists. Run 'battalion dispatch' first.")
    packet = result_packet(assignment, outcome, summary or f"Simulated execution returned {outcome}.", evidence)
    return consume_result_packet(workspace, packet, failure_type, reason, impact, recommendation, decision_action)


def runtime_status(workspace: Path) -> Dict[str, Any]:
    mission = read_yaml(workspace / "mission.yaml")
    ledger = read_yaml(workspace / "ledger.yaml")
    runtime = load_assignments(workspace)
    assignments = runtime["assignments"]
    return {
        "mission": mission,
        "current_phase": "runtime" if assignments else "planning",
        "assignments": assignments,
        "blocked_work": [item for item in assignments if item.get("status") in {"BLOCKED", "FAILED", "ABORTED"}],
        "completed_work": [item for item in assignments if item.get("status") == "COMPLETE"],
        "pending_work": [item for item in ledger.get("requirements", []) if not _closed_requirement(item)],
        "clarifications": ledger.get("clarifications", []),
        "recommendation": _recommendation(assignments, ledger),
    }


def _recommendation(assignments: List[Dict[str, Any]], ledger: Dict[str, Any]) -> str:
    active = _active_assignment(assignments)
    if active:
        return f"Execute active assignment {active['id']}."
    terminal_blocker = next((item for item in assignments if item.get("status") in {"FAILED", "ABORTED", "BLOCKED"}), None)
    if terminal_blocker:
        packet = terminal_blocker.get("abort_packet") or {}
        return packet.get("recommendation") or f"Resolve {terminal_blocker['id']} before continuing."
    if any(not _closed_requirement(item) for item in ledger.get("requirements", [])):
        return "Run battalion dispatch to assign the next requirement."
    return "All dispatchable requirements have terminal status. Run battalion assure."
