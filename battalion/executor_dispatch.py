import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import append_event, timestamp, write_yaml


SUPPORTED_EXECUTORS = {
    "codex": {
        "display_name": "Codex",
        "command": "codex",
        "args": ["exec"],
        "capabilities": ["native planning", "parallel sub-agents", "executor-specific capabilities"],
    },
    "claude-code": {
        "display_name": "Claude Code",
        "command": "claude",
        "args": ["-p"],
        "capabilities": ["native planning", "task decomposition", "parallel execution when supported"],
    },
    "copilot": {
        "display_name": "GitHub Copilot CLI",
        "command": "gh",
        "args": ["copilot", "suggest"],
        "capabilities": ["native planning", "task decomposition", "platform-specific execution behavior"],
    },
}

EXECUTOR_ALIASES = {
    "codex": "codex",
    "claude": "claude-code",
    "claude-code": "claude-code",
    "github-copilot": "copilot",
    "github-copilot-cli": "copilot",
    "copilot": "copilot",
}

SUPPORTED_MODES = {"standard", "auto"}


def normalize_executor(executor: str) -> str:
    normalized = (executor or "").strip().lower()
    if normalized not in EXECUTOR_ALIASES:
        supported = ", ".join(sorted(SUPPORTED_EXECUTORS))
        raise ValueError(f"Unsupported executor: {executor}. Supported executors: {supported}.")
    return EXECUTOR_ALIASES[normalized]


def dispatch_engineering_brief(workspace: Path, executor: str, mode: str = "standard") -> Dict[str, Any]:
    executor_id = normalize_executor(executor)
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"Unsupported dispatch mode: {mode}. Supported modes: {', '.join(sorted(SUPPORTED_MODES))}.")

    mission_plan_path = workspace / "mission-plan.md"
    if not mission_plan_path.is_file():
        raise ValueError("No engineering brief exists. Run battalion plan first to create .battalion/mission-plan.md.")

    mission_plan = mission_plan_path.read_text(encoding="utf-8")
    architecture_references = extract_architecture_references(mission_plan)
    missing = missing_architecture_references(workspace, architecture_references)
    if missing:
        raise ValueError(
            "Architecture reference filename not found: "
            + ", ".join(missing)
            + ". Create the referenced file(s) in the mission directory or regenerate the plan without those references."
        )

    dispatch_id = next_dispatch_id(workspace)
    package_dir = workspace / "dispatches" / dispatch_id
    package_dir.mkdir(parents=True, exist_ok=False)
    instructions = render_executor_wrapper(executor_id, mode, mission_plan, architecture_references)
    instructions_path = package_dir / "instructions.md"
    instructions_path.write_text(instructions, encoding="utf-8")

    started = time.monotonic()
    started_at = timestamp()
    command = invocation_command(executor_id, instructions_path, mode)
    append_event(workspace, "dispatch_started", {
        "dispatch_id": dispatch_id,
        "executor": executor_id,
        "mode": mode,
        "package": str(package_dir.relative_to(workspace)),
        "mission_plan": "mission-plan.md",
        "architecture_references": architecture_references,
    }, actor="dispatcher")
    try:
        completed = subprocess.run(command, cwd=workspace.parent)
        return_code = completed.returncode
    except FileNotFoundError as exc:
        metadata = dispatch_metadata(
            dispatch_id,
            executor_id,
            mode,
            command,
            package_dir,
            instructions_path,
            architecture_references,
            "FAILED",
            started_at,
            time.monotonic() - started,
            None,
        )
        metadata["error"] = f"Executor command not found: {command[0]}"
        write_yaml(package_dir / "metadata.yaml", metadata)
        append_event(workspace, "dispatch_completed", metadata, actor="dispatcher")
        raise ValueError(
            f"Executor command not found: {command[0]}. Install or configure {SUPPORTED_EXECUTORS[executor_id]['display_name']} and try again."
        ) from exc

    status = "COMPLETED" if return_code == 0 else "FAILED"
    metadata = dispatch_metadata(
        dispatch_id,
        executor_id,
        mode,
        command,
        package_dir,
        instructions_path,
        architecture_references,
        status,
        started_at,
        time.monotonic() - started,
        return_code,
    )
    write_yaml(package_dir / "metadata.yaml", metadata)
    append_event(workspace, "dispatch_completed", metadata, actor="dispatcher")
    return metadata


def next_dispatch_id(workspace: Path) -> str:
    dispatch_root = workspace / "dispatches"
    if not dispatch_root.exists():
        return "DSP-001"
    existing = []
    for path in dispatch_root.iterdir():
        if path.is_dir() and path.name.startswith("DSP-"):
            try:
                existing.append(int(path.name.removeprefix("DSP-")))
            except ValueError:
                continue
    return f"DSP-{(max(existing) if existing else 0) + 1:03d}"


def extract_architecture_references(mission_plan: str) -> List[str]:
    references: List[str] = []
    in_section = False
    for line in mission_plan.splitlines():
        stripped = line.strip()
        if stripped == "## Architecture References":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if in_section and stripped.startswith("- "):
            value = stripped[2:].strip()
            if value and not value.lower().startswith("no architecture reference"):
                references.append(value)
    return references


def missing_architecture_references(workspace: Path, references: List[str]) -> List[str]:
    missing = []
    mission_root = workspace.parent
    for reference in references:
        if not (mission_root / reference).is_file():
            missing.append(reference)
    return missing


def render_executor_wrapper(executor_id: str, mode: str, mission_plan: str, architecture_references: Optional[List[str]] = None) -> str:
    executor = SUPPORTED_EXECUTORS[executor_id]
    architecture_references = architecture_references or []
    auto_note = (
        "Auto mode is enabled. You may perform routine local engineering operations such as creating files, modifying files, switching local branches when required, running builds, executing tests, and using local tooling. "
        "Auto mode does not authorize git commit, git push, pull request creation, merge operations, deployment, or remote repository modification."
        if mode == "auto"
        else "Standard mode is enabled. Follow your normal executor configuration and approval flow."
    )
    architecture_block = "\n".join(f"- {item}" for item in architecture_references) if architecture_references else "- None supplied"
    capability_block = "\n".join(f"- {item}" for item in executor["capabilities"])
    return (
        f"# Battalion Dispatch Package — {executor['display_name']}\n\n"
        "You are receiving a Battalion engineering mission.\n\n"
        "## Dispatch Boundaries\n\n"
        "- Battalion Planning defines what must be built.\n"
        "- You determine how to implement the mission using your native capabilities.\n"
        "- Battalion Dispatch does not prescribe implementation strategy.\n"
        "- Do not modify `.battalion/mission-plan.md`.\n"
        "- Do not invoke `battalion assure`; assurance remains an explicit post-dispatch step.\n"
        "- Do not commit, push, open pull requests, merge, deploy, or modify remote repositories.\n\n"
        "## Execution Mode\n\n"
        f"{auto_note}\n\n"
        "## Executor Capabilities\n\n"
        f"{capability_block}\n\n"
        "Use these capabilities according to your existing user configuration. Battalion does not configure models, hooks, skills, MCP servers, repository permissions, or platform preferences.\n\n"
        "## Battalion Context\n\n"
        "Battalion provides only the immutable engineering brief and architecture reference filenames below. Use your own repository awareness to inspect and modify the working tree as needed.\n\n"
        "Architecture reference filenames:\n\n"
        f"{architecture_block}\n\n"
        "## Engineering Brief\n\n"
        "The following is the unchanged engineering specification generated by Battalion Planning.\n\n"
        "```markdown\n"
        f"{mission_plan.rstrip()}\n"
        "```\n"
    )


def invocation_command(executor_id: str, instructions_path: Path, mode: str) -> List[str]:
    executor = SUPPORTED_EXECUTORS[executor_id]
    prompt = f"Execute the Battalion dispatch package at {instructions_path}."
    if executor_id == "codex":
        command = [executor["command"], *executor["args"]]
        if mode == "auto":
            command.append("--full-auto")
        return [*command, prompt]
    if executor_id == "claude-code":
        command = [executor["command"], *executor["args"]]
        if mode == "auto":
            command.append("--dangerously-skip-permissions")
        return [*command, prompt]
    return [executor["command"], *executor["args"], prompt]


def dispatch_metadata(
    dispatch_id: str,
    executor_id: str,
    mode: str,
    command: List[str],
    package_dir: Path,
    instructions_path: Path,
    architecture_references: List[str],
    status: str,
    started_at: str,
    duration: float,
    return_code: Optional[int],
) -> Dict[str, Any]:
    return {
        "dispatch_id": dispatch_id,
        "executor": executor_id,
        "executor_name": SUPPORTED_EXECUTORS[executor_id]["display_name"],
        "mode": mode,
        "status": status,
        "return_code": return_code,
        "started_at": started_at,
        "completed_at": timestamp(),
        "duration_seconds": round(duration, 3),
        "mission_plan": "mission-plan.md",
        "package": str(package_dir.name),
        "instructions": str(instructions_path.relative_to(package_dir)),
        "architecture_references": architecture_references,
        "command": command,
        "next_step": "Run battalion assure after reviewing executor output.",
    }
