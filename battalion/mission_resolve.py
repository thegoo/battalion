import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .executor_dispatch import (
    SUPPORTED_EXECUTORS,
    SUPPORTED_MODES,
    invocation_command,
    invoke_executor,
    normalize_executor,
)
from .storage import append_event, read_yaml, timestamp, write_yaml


REQUIRED_RESOLVE_FILES = ("mission.yaml", "assessment.json", "mission-plan.md", "assurance.json")


def resolve_mission(
    workspace: Path,
    executor: Optional[str] = None,
    mode: str = "standard",
    output: Callable[[str], None] = print,
    heartbeat_interval: float = 30.0,
    poll_interval: float = 0.25,
) -> Dict[str, Any]:
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"Unsupported resolve mode: {mode}. Supported modes: {', '.join(sorted(SUPPORTED_MODES))}.")
    missing = [name for name in REQUIRED_RESOLVE_FILES if not (workspace / name).is_file()]
    if missing:
        if "assurance.json" in missing:
            raise ValueError("No Mission Assurance report exists. Run battalion assure before battalion resolve.")
        raise ValueError("Mission Resolve requires: " + ", ".join(REQUIRED_RESOLVE_FILES) + f". Missing: {', '.join(missing)}.")

    mission = read_yaml(workspace / "mission.yaml")
    assessment = _read_json(workspace / "assessment.json")
    mission_plan = (workspace / "mission-plan.md").read_text(encoding="utf-8")
    assurance_path = workspace / "assurance.json"
    assurance = _read_json(assurance_path)
    failed_checks = _failed_engineering_checks(assurance)
    engineering = assurance.get("engineering_result", {}) if isinstance(assurance, dict) else {}
    if engineering.get("status") == "GREEN" or not failed_checks:
        output("No engineering failures require resolution.")
        return {"created": False, "reason": "no_failed_engineering_findings", "package": None}

    executor_id = normalize_executor(executor) if executor else None
    resolve_id = next_resolution_id(workspace)
    package_dir = workspace / "resolutions" / resolve_id
    package_dir.mkdir(parents=True, exist_ok=False)
    instructions = render_resolution_instructions(mission, assessment, mission_plan, assurance, failed_checks)
    instructions_path = package_dir / "instructions.md"
    instructions_path.write_text(instructions, encoding="utf-8")

    metadata = resolution_metadata(
        resolve_id,
        executor_id,
        mode,
        package_dir,
        instructions_path,
        assurance_path,
        assurance,
        failed_checks,
        "PENDING",
        None,
        None,
        None,
    )
    write_yaml(package_dir / "metadata.yaml", metadata)
    append_event(workspace, "resolve_package_created", metadata, actor="mission_resolve")

    output("Mission Resolve package created.")
    output("")
    output(f"Resolution: {resolve_id}")
    output(f"Failed findings: {len(failed_checks)}")
    output(f"Package: .battalion/resolutions/{resolve_id}")

    if not executor_id:
        output("")
        output("Next:")
        output(f"battalion resolve --executor codex")
        return {"created": True, "metadata": metadata, "package": package_dir}

    executor_name = SUPPORTED_EXECUTORS[executor_id]["display_name"]
    output("")
    output("Starting executor...")
    output("")
    started = time.monotonic()
    started_at = timestamp()
    command = invocation_command(
        executor_id,
        instructions_path,
        mode,
        prompt=f"Execute the Battalion resolve package at {instructions_path}.",
    )
    metadata.update({
        "executor": executor_id,
        "executor_name": executor_name,
        "command": command,
        "started_at": started_at,
    })
    write_yaml(package_dir / "metadata.yaml", metadata)
    append_event(workspace, "resolve_started", metadata, actor="mission_resolve")
    try:
        return_code = invoke_executor(command, workspace.parent, started, heartbeat_interval, poll_interval, output)
    except FileNotFoundError as exc:
        metadata.update({
            "status": "FAILED",
            "return_code": None,
            "completed_at": timestamp(),
            "duration_seconds": round(time.monotonic() - started, 3),
            "error": f"Executor command not found: {command[0]}",
        })
        write_yaml(package_dir / "metadata.yaml", metadata)
        append_event(workspace, "resolve_completed", metadata, actor="mission_resolve")
        output("")
        output("Resolve failed.")
        output("")
        output(f"Executor: {executor_name}")
        output(f"Failure reason: Executor command not found: {command[0]}")
        output("Exit code: unavailable")
        output(f"Recommended action: Install or configure {executor_name} and try again.")
        raise ValueError(f"Executor command not found: {command[0]}. Install or configure {executor_name} and try again.") from exc

    status = "COMPLETED" if return_code == 0 else "FAILED"
    metadata.update({
        "status": status,
        "return_code": return_code,
        "completed_at": timestamp(),
        "duration_seconds": round(time.monotonic() - started, 3),
        "next_step": "Run battalion assure after reviewing executor corrections.",
    })
    write_yaml(package_dir / "metadata.yaml", metadata)
    append_event(workspace, "resolve_completed", metadata, actor="mission_resolve")
    output("")
    if status == "COMPLETED":
        output("Resolve complete.")
        output("")
        output(f"Executor: {executor_name}")
        output(f"Status: {status}")
        output(f"Duration: {metadata['duration_seconds']} seconds")
        output("")
        output("Resolution package:")
        output(f".battalion/resolutions/{resolve_id}")
        output("")
        output("Next:")
        output("battalion assure")
    else:
        output("Resolve failed.")
        output("")
        output(f"Executor: {executor_name}")
        output("Failure reason: Executor exited with a non-zero status.")
        output(f"Exit code: {return_code}")
        output("Recommended action: Review executor output above, correct the issue, and retry resolve.")
    return {"created": True, "metadata": metadata, "package": package_dir}


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def _failed_engineering_checks(assurance: Dict[str, Any]) -> List[Dict[str, Any]]:
    engineering = assurance.get("engineering_result", {}) if isinstance(assurance, dict) else {}
    checks = engineering.get("checks", []) if isinstance(engineering, dict) else []
    return [
        check for check in checks
        if isinstance(check, dict) and check.get("result") == "FAILED"
    ]


def next_resolution_id(workspace: Path) -> str:
    root = workspace / "resolutions"
    if not root.exists():
        return "RES-001"
    existing = []
    for path in root.iterdir():
        if path.is_dir() and path.name.startswith("RES-"):
            try:
                existing.append(int(path.name.removeprefix("RES-")))
            except ValueError:
                continue
    return f"RES-{(max(existing) if existing else 0) + 1:03d}"


def render_resolution_instructions(
    mission: Dict[str, Any],
    assessment: Dict[str, Any],
    mission_plan: str,
    assurance: Dict[str, Any],
    failed_checks: List[Dict[str, Any]],
) -> str:
    mission_title = mission.get("title", "Untitled mission") if isinstance(mission, dict) else "Untitled mission"
    mission_objective = mission.get("objective", "") if isinstance(mission, dict) else ""
    attributes = assessment.get("mission_attributes", []) if isinstance(assessment, dict) else []
    constraints = ", ".join(str(item) for item in attributes) if attributes else "None recorded"
    failed_block = "\n\n".join(render_failed_check(check) for check in failed_checks)
    return (
        "# Battalion Resolve Package\n\n"
        "You are receiving a Battalion implementation correction package.\n\n"
        "## Resolve Boundaries\n\n"
        "- Correct the implementation.\n"
        "- Do not expand scope.\n"
        "- Do not modify the mission.\n"
        "- Do not modify acceptance criteria.\n"
        "- Do not modify `.battalion/mission-plan.md`.\n"
        "- Do not regenerate requirements.\n"
        "- Do not replan the mission.\n"
        "- Do not weaken tests.\n"
        "- Only implement work necessary to satisfy failed engineering findings.\n"
        "- Do not commit, push, open pull requests, merge, deploy, or modify remote repositories.\n\n"
        "## Mission Summary\n\n"
        f"- Mission: {mission_title}\n"
        f"- Objective: {mission_objective}\n\n"
        "## Engineering Constraints\n\n"
        f"- Mission attributes: {constraints}\n"
        "- The original mission and mission plan remain authoritative.\n\n"
        "## Failed Engineering Findings\n\n"
        f"{failed_block}\n\n"
        "## Mission Success Reminder\n\n"
        "Success means the implementation satisfies the existing engineering contract and Mission Assurance no longer reports these failed engineering findings.\n\n"
        "## Original Mission Plan Reference\n\n"
        "The unchanged Battalion mission plan remains authoritative:\n\n"
        "```markdown\n"
        f"{mission_plan.rstrip()}\n"
        "\n```\n\n"
        "## Assurance Report Reference\n\n"
        f"- Engineering Result: {assurance.get('engineering_result', {}).get('status', 'UNKNOWN')}\n"
        f"- Overall Status: {assurance.get('status', 'UNKNOWN')}\n"
    )


def render_failed_check(check: Dict[str, Any]) -> str:
    return (
        f"### {check.get('requirement_id', 'UNKNOWN')} — {check.get('check_id', 'UNKNOWN')}\n\n"
        f"- Acceptance criterion: {check.get('criterion', '—')}\n"
        f"- Check type: {check.get('check_type', '—')}\n"
        f"- Expected: {json.dumps(check.get('expected'), sort_keys=True)}\n"
        f"- Observed: {json.dumps(check.get('observed'), sort_keys=True)}\n"
        f"- Evidence: {json.dumps(check.get('evidence'), sort_keys=True)}\n"
        f"- Finding: {check.get('finding', '—')}\n"
        f"- Recommendation: {check.get('recommendation', '—')}"
    )


def resolution_metadata(
    resolve_id: str,
    executor_id: Optional[str],
    mode: str,
    package_dir: Path,
    instructions_path: Path,
    assurance_path: Path,
    assurance: Dict[str, Any],
    failed_checks: List[Dict[str, Any]],
    status: str,
    started_at: Optional[str],
    duration: Optional[float],
    return_code: Optional[int],
) -> Dict[str, Any]:
    assurance_bytes = assurance_path.read_bytes()
    return {
        "resolution_id": resolve_id,
        "executor": executor_id,
        "executor_name": SUPPORTED_EXECUTORS[executor_id]["display_name"] if executor_id else None,
        "mode": mode,
        "status": status,
        "return_code": return_code,
        "started_at": started_at,
        "completed_at": None,
        "duration_seconds": round(duration, 3) if duration is not None else None,
        "mission": "mission.yaml",
        "assessment": "assessment.json",
        "mission_plan": "mission-plan.md",
        "assurance_report": "assurance.json",
        "assurance_sha256": hashlib.sha256(assurance_bytes).hexdigest(),
        "assurance_engineering_result": assurance.get("engineering_result", {}).get("status"),
        "package": str(package_dir.name),
        "instructions": str(instructions_path.relative_to(package_dir)),
        "failed_findings": [
            {
                "check_id": check.get("check_id"),
                "requirement_id": check.get("requirement_id"),
                "criterion": check.get("criterion"),
                "expected": check.get("expected"),
                "observed": check.get("observed"),
                "evidence": check.get("evidence"),
                "finding": check.get("finding"),
                "recommendation": check.get("recommendation"),
            }
            for check in failed_checks
        ],
        "command": None,
        "next_step": "Run battalion assure after applying corrections.",
    }
