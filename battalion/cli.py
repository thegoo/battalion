import argparse
import sys
from pathlib import Path

from .agents import standing_team
from .assurance import assure
from .mission_analyst import generate_mission_contract
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
        if ledger["requirements"]:
            raise SystemExit("A mission contract already contains requirements. Use --requirement to add one manually.")
        mission = read_yaml(workspace / "mission.yaml")
        mission_prompt = mission.get("mission_prompt") or mission.get("original_prompt")
        if not isinstance(mission_prompt, str) or not mission_prompt.strip():
            raise SystemExit("Mission prompt is missing or invalid. Reinitialize the mission with a valid prompt.")
        contract = generate_mission_contract(mission["id"], mission_prompt)
        write_yaml(workspace / "ledger.yaml", contract)
        append_event(workspace, "mission_contract_generated", {
            "mission_id": mission["id"],
            "generated_by": "mission_analyst",
            "requirement_ids": [requirement["id"] for requirement in contract["requirements"]],
            "assumption_count": len(contract["assumptions"]),
            "risk_count": len(contract["risks"]),
            "clarification_count": len(contract["clarifications"]),
            "constraint_count": sum(len(values) for values in contract["constraints"].values()),
        })
        append_event(workspace, "plan_created", {"requirement_count": len(contract["requirements"])})
        print("Mission Analyst generated the mission contract:\n")
        for requirement in contract["requirements"]:
            print(f"{requirement['id']} — {requirement['statement']}")
            for criterion in requirement["acceptance"]:
                print(f"  Acceptance: {criterion}")
            print(f"  Prompt: {requirement['traceability']['prompt_excerpt']}")
            print(f"  Why: {requirement['traceability']['rationale']}")
            for review in requirement["required_reviews"]:
                print(f"  Review: {review['reviewer']} ({review['reason']})")
        print("\nExtracted constraints:")
        for category, values in contract["constraints"].items():
            for constraint in values:
                print(f"- {constraint['id']} [{category}]: {constraint['statement']}")
        print("\nAssumptions:")
        for assumption in contract["assumptions"]:
            print(f"- {assumption['id']}: {assumption['statement']}")
        print("Risks:")
        for risk in contract["risks"]:
            print(f"- {risk['id']}: {risk['statement']}")
        print("Clarifications:")
        if contract["clarifications"]:
            for clarification in contract["clarifications"]:
                print(f"- {clarification['id']} [{clarification['status']}]: {clarification['question']}")
        else:
            print("- None required")
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


def dispatch(args, cwd):
    workspace = workspace_or_exit(cwd)
    ledger = read_yaml(workspace / "ledger.yaml"); team = read_yaml(workspace / "agents.yaml")["agents"]
    planned = []
    for req in ledger["requirements"]:
        if req.get("status") == "proposed": req["status"] = "planned"; planned.append(req["id"])
    write_yaml(workspace / "ledger.yaml", ledger)
    append_event(workspace, "dispatch_simulated", {"requirements": planned, "reviewers": [a["id"] for a in team]})
    print(f"Simulated dispatch to {len(team)} standing agents; planned {len(planned)} requirement(s).")


def assurance(args, cwd):
    workspace = workspace_or_exit(cwd)
    result = assure(workspace)
    if (workspace / "events.jsonl").is_file(): append_event(workspace, "assurance_completed", result.to_dict())
    print(f"Status: {result.status}\nRecommendation: {result.recommendation}\nConfidence: {result.confidence}\nFindings:")
    for finding in result.findings: print(f"- {finding}")


def report(args, cwd):
    workspace = workspace_or_exit(cwd)
    try: content = render_report(workspace)
    except ValueError as exc: raise SystemExit(str(exc)) from exc
    target = workspace / "reports" / "mission-report.md"; target.parent.mkdir(exist_ok=True); target.write_text(content, encoding="utf-8")
    append_event(workspace, "report_generated", {"path": str(target.relative_to(cwd))})
    print(f"Generated {target}")


def parser():
    result = argparse.ArgumentParser(prog="battalion", description="Battalion v0.1.4 traceable Mission Analyst governance")
    commands = result.add_subparsers(dest="command", required=True)
    p = commands.add_parser("init"); p.add_argument("--title"); p.add_argument("--objective"); p.add_argument("--prompt")
    p = commands.add_parser("plan"); p.add_argument("--requirement", help="Add one requirement manually instead of generating a mission contract")
    p.add_argument("--acceptance", action="append", help="Acceptance criterion; repeat for multiple criteria")
    p.add_argument("--review", action="append", help="Required standing-team reviewer id; repeat for multiple reviews")
    commands.add_parser("dispatch"); commands.add_parser("assure"); commands.add_parser("report")
    return result


def main(argv=None, cwd=None):
    args = parser().parse_args(argv); cwd = Path.cwd() if cwd is None else Path(cwd)
    {"init": init, "plan": plan, "dispatch": dispatch, "assure": assurance, "report": report}[args.command](args, cwd)


if __name__ == "__main__": main()
