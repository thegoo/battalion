import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


WORKSPACE = ".battalion"


class BattalionYamlDumper(yaml.SafeDumper):
    pass


def _represent_string(dumper, value):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


BattalionYamlDumper.add_representer(str, _represent_string)


def root(path: Path) -> Path:
    return path / WORKSPACE


def read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot read {path.name}: {exc}") from exc


def write_yaml(path: Path, data: Any) -> None:
    path.write_text(
        yaml.dump(data, Dumper=BattalionYamlDumper, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_event(workspace: Path, event_type: str, details=None, actor="battalion_cli") -> None:
    event = {"timestamp": timestamp(), "type": event_type, "actor": actor, "details": details or {}}
    with (workspace / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, separators=(",", ":")) + "\n")
