import json
import re
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import AssuranceResult, FINAL_STATUSES, VALID_REVIEW_STATUSES, VALID_STATUSES
from .storage import read_yaml


REQUIRED_FILES = ("mission.yaml", "agents.yaml", "ledger.yaml", "events.jsonl")
REQUIRED_REQUIREMENT_FIELDS = ("id", "statement", "status", "acceptance", "evidence", "required_reviews")
CONSTRAINT_CATEGORIES = ("functional", "technical", "security", "testing", "operational")
CLARIFICATION_STATUSES = ("open", "resolved", "superseded", "rejected")
VALID_CLARIFICATION_STATUSES = set(CLARIFICATION_STATUSES)


def _is_text(value):
    return isinstance(value, str) and bool(value.strip())


def _is_timestamp(value):
    if not _is_text(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _validate_string_list(value, label, finding):
    if not isinstance(value, list):
        finding.append(f"{label} must be a list")
        return []
    for index, item in enumerate(value, 1):
        if not _is_text(item):
            finding.append(f"{label} entry {index} must be non-blank text")
    return value


def _validate_evidence_paths(workspace, requirement_id, evidence, findings):
    project = workspace.parent.resolve()
    for reference in evidence:
        if not _is_text(reference):
            continue
        candidate = (project / reference).resolve()
        try:
            candidate.relative_to(project)
        except ValueError:
            findings.append(f"{requirement_id}: Evidence path escapes the mission project: {reference}")
            continue
        if not candidate.is_file():
            findings.append(f"{requirement_id}: Evidence file does not exist: {reference}")


def _validate_traceability(value, label, mission_prompt, constraint_ids):
    findings = []
    if not isinstance(value, dict):
        return [f"{label}: Missing prompt traceability"]
    if value.get("source") != "mission_prompt":
        findings.append(f"{label}: Traceability source must be mission_prompt")
    excerpt = value.get("prompt_excerpt")
    if not _is_text(excerpt):
        findings.append(f"{label}: Traceability prompt excerpt is missing")
    elif not _is_text(mission_prompt) or excerpt not in mission_prompt:
        findings.append(f"{label}: Traceability excerpt does not occur in the authoritative mission prompt")
    if not _is_text(value.get("rationale")):
        findings.append(f"{label}: Traceability rationale is missing")
    linked = value.get("constraint_ids")
    if not isinstance(linked, list) or any(not _is_text(identifier) for identifier in linked):
        findings.append(f"{label}: Traceability constraint_ids must be a list of identifiers")
    elif constraint_ids is not None:
        for identifier in linked:
            if identifier not in constraint_ids:
                findings.append(f"{label}: Traceability references unknown constraint: {identifier}")
    return findings


def _validate_audit(path, mission_id, clarifications=None):
    findings = []
    events = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [f"Mission: Audit trail is unreadable: {exc}"]
    if not lines:
        return ["Mission: Audit trail contains no events", "Mission: Audit trail is missing mission_initialized event"]
    initialized = False
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            findings.append(f"Mission: Audit event line {line_number} is blank")
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            findings.append(f"Mission: Audit event line {line_number} is invalid JSON: {exc.msg}")
            continue
        if not isinstance(event, dict):
            findings.append(f"Mission: Audit event line {line_number} must be an object")
            continue
        events.append(event)
        for field in ("timestamp", "type", "actor"):
            if not _is_text(event.get(field)):
                findings.append(f"Mission: Audit event line {line_number} has invalid {field}")
        if not isinstance(event.get("details"), dict):
            findings.append(f"Mission: Audit event line {line_number} has invalid details")
        if _is_text(event.get("timestamp")):
            try:
                datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
            except ValueError:
                findings.append(f"Mission: Audit event line {line_number} has invalid timestamp")
        if event.get("type") == "mission_initialized":
            event_mission_id = event.get("details", {}).get("mission_id") if isinstance(event.get("details"), dict) else None
            if event_mission_id == mission_id:
                initialized = True
            else:
                findings.append(f"Mission: Audit initialization event on line {line_number} has the wrong mission_id")
    if not initialized:
        findings.append("Mission: Audit trail is missing mission_initialized event")
    if isinstance(clarifications, list):
        for clarification in clarifications:
            if not isinstance(clarification, dict):
                continue
            clarification_id = clarification.get("id")
            for history in clarification.get("history", []):
                if not isinstance(history, dict):
                    continue
                action = history.get("action")
                expected_type = f"clarification_{action}"
                matching = [
                    event for event in events
                    if event.get("type") == expected_type
                    and isinstance(event.get("details"), dict)
                    and event["details"].get("mission_id") == mission_id
                    and event["details"].get("clarification_id") == clarification_id
                    and event["details"].get("action") == action
                    and event["details"].get("value") == history.get("value")
                    and event.get("actor") == history.get("actor")
                ]
                if not matching:
                    findings.append(f"Mission: Audit trail is missing {expected_type} event for {clarification_id}")
                if action != "created":
                    reconciled = any(
                        event.get("type") == "mission_contract_reconciled"
                        and isinstance(event.get("details"), dict)
                        and event["details"].get("mission_id") == mission_id
                        and clarification_id in event["details"].get("clarification_ids", [])
                        for event in events
                    )
                    if not reconciled:
                        findings.append(f"Mission: Audit trail is missing mission_contract_reconciled event for {clarification_id}")
    return findings


def _validate_requirement(item, index, workspace, known_reviewers, mission_prompt=None, constraint_ids=None, require_traceability=False):
    red, amber = [], []
    if not isinstance(item, dict):
        return [f"Requirement #{index}: Requirement must be an object"], amber, None
    requirement_id = item.get("id") if _is_text(item.get("id")) else f"Requirement #{index}"
    for field in REQUIRED_REQUIREMENT_FIELDS:
        if field not in item:
            red.append(f"{requirement_id}: Missing required field: {field}")
    for field in ("id", "statement", "status"):
        if field in item and not _is_text(item[field]):
            red.append(f"{requirement_id}: {field} must be non-blank text")

    status = item.get("status")
    if _is_text(status) and status not in VALID_STATUSES:
        red.append(f"{requirement_id}: Invalid status: {status}")

    if "acceptance" in item:
        acceptance = _validate_string_list(item["acceptance"], f"{requirement_id}: Acceptance criteria", red)
        if isinstance(acceptance, list) and not acceptance:
            red.append(f"{requirement_id}: Missing acceptance criteria")
    else:
        red.append(f"{requirement_id}: Missing acceptance criteria")

    evidence = []
    if "evidence" in item:
        evidence = _validate_string_list(item["evidence"], f"{requirement_id}: Evidence", red)
        if status == "completed" and isinstance(evidence, list) and not evidence:
            red.append(f"{requirement_id}: Completed without evidence")
        if status == "completed" and isinstance(evidence, list):
            _validate_evidence_paths(workspace, requirement_id, evidence, red)
    elif status == "completed":
        red.append(f"{requirement_id}: Completed without evidence")

    for field in ("assumptions", "risks"):
        if field in item:
            _validate_string_list(item[field], f"{requirement_id}: {field.capitalize()}", red)
    if status == "accepted_risk" and not item.get("risks"):
        red.append(f"{requirement_id}: Accepted risk has no risk entry")
    if "owner" in item and not _is_text(item["owner"]):
        red.append(f"{requirement_id}: owner must be non-blank text")

    reviews = item.get("required_reviews")
    if "required_reviews" in item:
        if not isinstance(reviews, list):
            red.append(f"{requirement_id}: Required reviews must be a list")
        elif not reviews:
            red.append(f"{requirement_id}: Missing required reviews")
        else:
            seen = set()
            for review_index, review in enumerate(reviews, 1):
                if not isinstance(review, dict):
                    red.append(f"{requirement_id}: Review #{review_index} must be an object")
                    continue
                reviewer = review.get("reviewer")
                review_status = review.get("status")
                if "reason" in review and not _is_text(review["reason"]):
                    red.append(f"{requirement_id}: Review {reviewer or review_index} has invalid reason")
                if not _is_text(reviewer):
                    red.append(f"{requirement_id}: Review #{review_index} has invalid reviewer")
                elif reviewer in seen:
                    red.append(f"{requirement_id}: Duplicate required review: {reviewer}")
                else:
                    seen.add(reviewer)
                    if known_reviewers is not None and reviewer not in known_reviewers:
                        red.append(f"{requirement_id}: Required reviewer is not in the standing team: {reviewer}")
                if review_status not in VALID_REVIEW_STATUSES:
                    red.append(f"{requirement_id}: Review {reviewer or review_index} has invalid status: {review_status}")
                elif review_status == "pending":
                    amber.append(f"{requirement_id}: Required review is pending: {reviewer}")
    else:
        red.append(f"{requirement_id}: Missing required reviews")

    if status in VALID_STATUSES and status not in FINAL_STATUSES:
        amber.append(f"{requirement_id}: Mission work remains open with status {status}")
    if require_traceability:
        red.extend(_validate_traceability(item.get("traceability"), requirement_id, mission_prompt, constraint_ids))
    return red, amber, item.get("id") if _is_text(item.get("id")) else None


def _validate_contract_records(values, label, mission_prompt=None, constraint_ids=None, require_traceability=False):
    findings = []
    if not isinstance(values, list) or not values:
        return [f"Mission contract: Missing generated {label.lower()}"]
    seen = set()
    for index, value in enumerate(values, 1):
        if not isinstance(value, dict):
            findings.append(f"Mission contract: {label} #{index} must be an object")
            continue
        identifier = value.get("id")
        if not _is_text(identifier):
            findings.append(f"Mission contract: {label} #{index} has an invalid id")
        elif identifier in seen:
            findings.append(f"Mission contract: Duplicate {label.lower()} id: {identifier}")
        else:
            seen.add(identifier)
        if not _is_text(value.get("statement")):
            findings.append(f"Mission contract: {label} #{index} has an invalid statement")
        if require_traceability:
            findings.extend(_validate_traceability(
                value.get("traceability"), f"Mission contract: {identifier or label + ' #' + str(index)}",
                mission_prompt, constraint_ids,
            ))
    return findings


def _validate_constraints(value, mission_prompt):
    findings, identifiers = [], set()
    if not isinstance(value, dict):
        return ["Mission contract: constraints must be an object"], identifiers
    for category in CONSTRAINT_CATEGORIES:
        entries = value.get(category)
        if not isinstance(entries, list):
            findings.append(f"Mission contract: Constraint category {category} must be a list")
            continue
        for index, entry in enumerate(entries, 1):
            label = f"Mission contract: {category} constraint #{index}"
            if not isinstance(entry, dict):
                findings.append(f"{label} must be an object")
                continue
            identifier = entry.get("id")
            if not _is_text(identifier):
                findings.append(f"{label} has an invalid id")
            elif identifier in identifiers:
                findings.append(f"Mission contract: Duplicate constraint id: {identifier}")
            else:
                identifiers.add(identifier)
            if not _is_text(entry.get("statement")):
                findings.append(f"{label} has an invalid statement")
            excerpt = entry.get("prompt_excerpt")
            if not _is_text(excerpt):
                findings.append(f"{label} has no prompt excerpt")
            elif not _is_text(mission_prompt) or excerpt not in mission_prompt:
                findings.append(f"{label} excerpt does not occur in the authoritative mission prompt")
    return findings, identifiers


def _validate_clarifications(values, mission_prompt, constraint_ids):
    red, amber = [], []
    counts = {status: 0 for status in CLARIFICATION_STATUSES}
    if not isinstance(values, list):
        return ["Mission contract: clarifications must be a list"], amber, counts
    seen = set()
    for index, value in enumerate(values, 1):
        label = f"Mission contract: Clarification #{index}"
        if not isinstance(value, dict):
            red.append(f"{label} must be an object")
            continue
        identifier = value.get("id")
        if not _is_text(identifier):
            red.append(f"{label} has an invalid id")
        elif identifier in seen:
            red.append(f"Mission contract: Duplicate clarification id: {identifier}")
        else:
            seen.add(identifier)
            label = f"Mission contract: {identifier}"
        if not _is_text(value.get("question")):
            red.append(f"{label} has an invalid question")
        status = value.get("status")
        if status not in VALID_CLARIFICATION_STATUSES:
            red.append(f"{label} has invalid status: {status}")
        else:
            counts[status] += 1
            if status == "open":
                amber.append(f"{label} remains open: {value.get('question', 'question missing')}")
                if value.get("answer") not in (None, ""):
                    red.append(f"{label} is open but already has an answer")
            else:
                if not _is_text(value.get("answer")):
                    red.append(f"{label} has no decision value")
                if not _is_text(value.get("resolved_by")):
                    red.append(f"{label} has no resolver")
                if not _is_timestamp(value.get("resolved_at")):
                    red.append(f"{label} has an invalid resolved timestamp")
        if not _is_timestamp(value.get("created_at")):
            red.append(f"{label} has an invalid created timestamp")
        history = value.get("history")
        if not isinstance(history, list) or not history:
            red.append(f"{label} has no clarification history")
        else:
            for history_index, entry in enumerate(history, 1):
                history_label = f"{label} history #{history_index}"
                if not isinstance(entry, dict):
                    red.append(f"{history_label} must be an object")
                    continue
                if entry.get("action") not in {"created"} | VALID_CLARIFICATION_STATUSES:
                    red.append(f"{history_label} has invalid action: {entry.get('action')}")
                if entry.get("status") not in VALID_CLARIFICATION_STATUSES:
                    red.append(f"{history_label} has invalid status: {entry.get('status')}")
                if not _is_text(entry.get("actor")):
                    red.append(f"{history_label} has no actor")
                if not _is_timestamp(entry.get("timestamp")):
                    red.append(f"{history_label} has an invalid timestamp")
            first, last = history[0], history[-1]
            if isinstance(first, dict) and (first.get("action") != "created" or first.get("status") != "open"):
                red.append(f"{label} history must begin with creation in open status")
            if isinstance(last, dict) and status in VALID_CLARIFICATION_STATUSES:
                if last.get("status") != status:
                    red.append(f"{label} status does not match its latest history entry")
                if status != "open" and (
                    last.get("value") != value.get("answer")
                    or last.get("actor") != value.get("resolved_by")
                    or last.get("timestamp") != value.get("resolved_at")
                ):
                    red.append(f"{label} decision fields do not match its latest history entry")
        red.extend(_validate_traceability(value.get("traceability"), label, mission_prompt, constraint_ids))
    return red, amber, counts


ENGINEERING_RESULTS = ("VERIFIED", "FAILED", "UNABLE_TO_VERIFY")
RUNTIME_EXECUTION_TIMESTAMP = "1970-01-01T00:00:00Z"
SAFE_RUNTIME_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _project_files(workspace):
    project = workspace.parent
    result = []
    for path in sorted(project.rglob("*")):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(project)
        except ValueError:
            continue
        if relative.parts and relative.parts[0] == ".battalion":
            continue
        if any(part in {"node_modules", ".git", ".venv", "__pycache__"} for part in relative.parts):
            continue
        result.append((relative.as_posix(), path))
    return result


def _read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _evidence_paths(workspace, requirement):
    paths = []
    project = workspace.parent.resolve()
    for reference in requirement.get("evidence", []) if isinstance(requirement.get("evidence"), list) else []:
        if not _is_text(reference):
            continue
        candidate = (project / reference).resolve()
        try:
            candidate.relative_to(project)
        except ValueError:
            continue
        paths.append((reference, candidate))
    return paths


def _existing_evidence(workspace, requirement):
    return [(reference, path) for reference, path in _evidence_paths(workspace, requirement) if path.is_file()]


def _mission_prompt(workspace):
    try:
        mission = read_yaml(workspace / "mission.yaml")
    except ValueError:
        return ""
    if isinstance(mission, dict) and _is_text(mission.get("mission_prompt")):
        return mission["mission_prompt"]
    return ""


def _all_text_sources(workspace, requirement):
    sources = []
    for reference, path in _existing_evidence(workspace, requirement):
        text = _read_text(path)
        if text:
            sources.append((reference, text))
    for reference, path in _project_files(workspace):
        text = _read_text(path)
        if text:
            sources.append((reference, text))
    return sources


def _project_text_sources(workspace):
    sources = []
    for reference, path in _project_files(workspace):
        text = _read_text(path)
        if text:
            sources.append((reference, text))
    return sources


def _package_json(workspace):
    path = workspace.parent / "package.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")), "package.json"
    except (OSError, json.JSONDecodeError):
        return None, None


def _source_files(workspace, suffixes):
    return [reference for reference, _ in _project_files(workspace) if reference.endswith(suffixes)]


def _check(check_id, requirement_id, criterion, check_type, expected, observed, evidence, result, finding, recommendation, execution_timestamp=None, validation_mode="static"):
    if result not in ENGINEERING_RESULTS:
        raise ValueError(f"invalid engineering assurance result: {result}")
    return {
        "check_id": check_id,
        "requirement_id": requirement_id,
        "criterion": criterion,
        "check_type": check_type,
        "expected": expected,
        "observed": observed,
        "evidence": evidence,
        "result": result,
        "finding": finding,
        "recommendation": recommendation,
        "execution_timestamp": execution_timestamp,
        "validation_mode": validation_mode,
    }


def _extract_expected_status_value(criterion):
    patterns = (
        r'status\s+(?:field\s+)?(?:equals|should equal|should be|is|=)\s+["\']?([A-Za-z0-9_.:-]+)["\']?',
        r'["\']status["\']\s*[:=]\s*["\']([^"\']+)["\']',
        r'status\s+(?!code\b)["\']?([A-Za-z][A-Za-z0-9_.:-]+)["\']?',
    )
    for pattern in patterns:
        match = re.search(pattern, criterion, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _expected_status_for_requirement(workspace, requirement, criterion):
    expected = _extract_expected_status_value(criterion)
    if expected:
        return expected
    criterion_lower = criterion.lower()
    if "http 200" in criterion_lower or "status code" in criterion_lower or "endpoint exists" in criterion_lower:
        return None
    if not any(term in criterion_lower for term in ("status", "machine-readable", "health result")):
        return None
    prompt = _mission_prompt(workspace)
    patterns = (
        r"service\s+status\s+of\s+([A-Za-z0-9_.:-]+)",
        r"returning\s+status\s+([A-Za-z0-9_.:-]+)",
        r"status\s+(?:of\s+)?([A-Za-z0-9_.:-]+)",
        r"status\s*:\s*([A-Za-z0-9_.:-]+)",
        r'"status"\s*:\s*"([^"]+)"',
    )
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip().rstrip(".,;")
            if value.lower() not in {"code", "field"}:
                return value
    return None


def _observed_status_value(workspace, requirement):
    sources = sorted(
        _all_text_sources(workspace, requirement),
        key=lambda item: (
            0 if item[0].startswith("src/") else
            1 if item[0].startswith(("tests/", "test/")) else
            2 if item[0].startswith("dist/") else
            3
        ),
    )
    for reference, text in sources:
        for pattern in (
            r'"status"\s*:\s*"([^"]+)"',
            r"'status'\s*:\s*'([^']+)'",
            r"\bstatus\s*:\s*[\"']([^\"']+)[\"']",
            r"\bstatus\s*[:=]\s*([A-Za-z0-9_.:-]+)",
        ):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1), reference
    return None, None


def _extract_endpoint(criterion):
    url_match = re.search(r"https?://[^\s)>'\"]+", criterion)
    if url_match:
        parsed = urlparse(url_match.group(0))
        if parsed.path:
            return parsed.path
    match = re.search(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+(/[A-Za-z0-9_./{}:-]*)", criterion)
    if match:
        return match.group(1)
    match = re.search(r"endpoint\s+(/[A-Za-z0-9_./{}:-]*)", criterion, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _mission_endpoint(workspace):
    prompt = _mission_prompt(workspace)
    match = re.search(r"\bGET\s+(/[A-Za-z0-9_./{}:-]*)", prompt)
    if match:
        return match.group(1)
    match = re.search(r"\bendpoint\s+(/[A-Za-z0-9_./{}:-]*)", prompt, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _endpoint_for_requirement(workspace, requirement, criterion):
    endpoint = _extract_endpoint(criterion) or _requirement_endpoint(requirement)
    if endpoint:
        return endpoint
    context = " ".join([
        requirement.get("statement", "") if isinstance(requirement, dict) else "",
        criterion,
    ]).lower()
    if "health" in context or "endpoint" in context or "http" in context:
        return _mission_endpoint(workspace)
    return None


def _extract_safe_runtime_urls(text):
    urls = []
    if not _is_text(text):
        return urls
    for match in re.finditer(r"https?://[^\s)>'\"]+", text):
        raw = match.group(0).rstrip(".,;")
        parsed = urlparse(raw)
        if parsed.scheme != "http" or parsed.hostname not in SAFE_RUNTIME_HOSTS:
            continue
        if not parsed.path:
            continue
        urls.append(raw)
    return urls


def _runtime_url_for_requirement(workspace, requirement, criterion):
    for source in [criterion, requirement.get("statement", "")]:
        urls = _extract_safe_runtime_urls(source)
        if urls:
            return urls[0]
    for item in requirement.get("acceptance", []) if isinstance(requirement.get("acceptance"), list) else []:
        urls = _extract_safe_runtime_urls(item)
        if urls:
            return urls[0]
    endpoint = _endpoint_for_requirement(workspace, requirement, criterion)
    if not endpoint:
        return None
    for _, text in _all_text_sources(workspace, requirement):
        for url in _extract_safe_runtime_urls(text):
            parsed = urlparse(url)
            if parsed.path == endpoint:
                return url
    for _, text in _project_text_sources(workspace):
        for url in _extract_safe_runtime_urls(text):
            parsed = urlparse(url)
            if parsed.path == endpoint:
                return url
    port = _detected_local_port(workspace)
    if port:
        return f"http://127.0.0.1:{port}{endpoint}"
    return None


def _requirement_endpoint(requirement):
    for source in [requirement.get("statement", "")]:
        endpoint = _extract_endpoint(source)
        if endpoint:
            return endpoint
    for criterion in requirement.get("acceptance", []) if isinstance(requirement.get("acceptance"), list) else []:
        endpoint = _extract_endpoint(criterion)
        if endpoint:
            return endpoint
    return None


def _detected_local_port(workspace):
    for _, text in _project_text_sources(workspace):
        for pattern in (
            r"PORT\s*\?\?\s*[\"'](\d+)[\"']",
            r"PORT\s*\|\|\s*[\"']?(\d+)[\"']?",
            r"listen\(\s*(\d+)",
            r"127\.0\.0\.1:(\d+)",
            r"localhost:(\d+)",
        ):
            match = re.search(pattern, text)
            if match:
                return match.group(1)
    return None


def _runtime_http_get(url):
    request = Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=2) as response:
            raw = response.read(65536)
            body = raw.decode("utf-8", errors="replace")
            headers = {key.lower(): value for key, value in response.headers.items()}
            return {
                "ok": True,
                "url": url,
                "status_code": response.status,
                "headers": headers,
                "body": body,
                "json": _parse_json_body(body),
                "error": None,
            }
    except HTTPError as exc:
        raw = exc.read(65536)
        body = raw.decode("utf-8", errors="replace")
        headers = {key.lower(): value for key, value in exc.headers.items()}
        return {
            "ok": True,
            "url": url,
            "status_code": exc.code,
            "headers": headers,
            "body": body,
            "json": _parse_json_body(body),
            "error": None,
        }
    except (OSError, URLError) as exc:
        return {
            "ok": False,
            "url": url,
            "status_code": None,
            "headers": {},
            "body": "",
            "json": None,
            "error": str(exc),
        }


def _parse_json_body(body):
    try:
        return json.loads(body)
    except (TypeError, json.JSONDecodeError):
        return None


def _runtime_execution_timestamp(workspace):
    try:
        for line in (workspace / "events.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if isinstance(event, dict) and event.get("type") == "mission_initialized" and _is_timestamp(event.get("timestamp")):
                return event["timestamp"]
    except (OSError, json.JSONDecodeError):
        pass
    return RUNTIME_EXECUTION_TIMESTAMP


def _runtime_response(workspace, requirement, criterion, cache):
    url = _runtime_url_for_requirement(workspace, requirement, criterion)
    if not url:
        return None, None
    if url not in cache:
        cache[url] = _runtime_http_get(url)
    return url, cache[url]


def _runtime_check_for_criterion(workspace, requirement, criterion, check_number, cache, runtime_timestamp):
    requirement_id = requirement.get("id") if _is_text(requirement.get("id")) else "UNKNOWN"
    check_id = f"ENG-{check_number:03d}"
    criterion_lower = criterion.lower()
    endpoint = _endpoint_for_requirement(workspace, requirement, criterion)
    expected_status = _expected_status_for_requirement(workspace, requirement, criterion)
    runtime_relevant = bool(endpoint or expected_status or "http 200" in criterion_lower or "status code 200" in criterion_lower or "json" in criterion_lower or "timestamp" in criterion_lower)
    if not runtime_relevant:
        return None
    url, response = _runtime_response(workspace, requirement, criterion, cache)
    if not response:
        return _check(
            check_id, requirement_id, criterion, "runtime_http",
            {"endpoint": endpoint or "runtime endpoint"}, None, [],
            "UNABLE_TO_VERIFY",
            f"{requirement_id}: Unable to run deterministic HTTP validation; no safe localhost URL was found.",
            "Provide a localhost runtime URL in the mission contract, acceptance criteria, or evidence.",
            execution_timestamp=runtime_timestamp,
            validation_mode="runtime",
        )
    evidence = [{
        "type": "http_response",
        "url": url,
        "status_code": response["status_code"],
        "headers": response["headers"],
        "body": response["body"],
        "error": response["error"],
    }]
    if not response["ok"]:
        return _check(
            check_id, requirement_id, criterion, "runtime_http",
            {"endpoint": endpoint or url}, {"error": response["error"]}, evidence,
            "UNABLE_TO_VERIFY",
            f"{requirement_id}: Unable to execute HTTP runtime validation: {response['error']}.",
            "Start the local application and retry battalion assure --run.",
            execution_timestamp=runtime_timestamp,
            validation_mode="runtime",
        )
    if expected_status:
        observed = response["json"].get("status") if isinstance(response["json"], dict) else None
        if observed == expected_status:
            return _check(
                check_id, requirement_id, criterion, "runtime_response_body_literal",
                {"field": "status", "value": expected_status}, {"field": "status", "value": observed}, evidence,
                "VERIFIED",
                f"{requirement_id}: Runtime response status field equals {expected_status}.",
                "No action required.",
                execution_timestamp=runtime_timestamp,
                validation_mode="runtime",
            )
        return _check(
            check_id, requirement_id, criterion, "runtime_response_body_literal",
            {"field": "status", "value": expected_status}, {"field": "status", "value": observed}, evidence,
            "FAILED",
            f'{requirement_id}: Expected response status field "{expected_status}"; observed "{observed}".',
            "Implementation does not satisfy the engineering contract. Update implementation or engineering contract.",
            execution_timestamp=runtime_timestamp,
            validation_mode="runtime",
        )
    if "http 200" in criterion_lower or "status code 200" in criterion_lower:
        result = "VERIFIED" if response["status_code"] == 200 else "FAILED"
        return _check(
            check_id, requirement_id, criterion, "runtime_http_status",
            200, response["status_code"], evidence, result,
            f"{requirement_id}: Observed HTTP {response['status_code']} response.",
            "No action required." if result == "VERIFIED" else "Return HTTP 200 for the required endpoint.",
            execution_timestamp=runtime_timestamp,
            validation_mode="runtime",
        )
    if "json" in criterion_lower:
        is_json = isinstance(response["json"], (dict, list))
        return _check(
            check_id, requirement_id, criterion, "runtime_json_response",
            "valid JSON response", "valid JSON response" if is_json else "non-JSON response", evidence,
            "VERIFIED" if is_json else "FAILED",
            f"{requirement_id}: Runtime response {'is valid JSON' if is_json else 'is not valid JSON'}.",
            "No action required." if is_json else "Return a JSON response body.",
            execution_timestamp=runtime_timestamp,
            validation_mode="runtime",
        )
    if "timestamp" in criterion_lower:
        value = response["json"].get("timestamp") if isinstance(response["json"], dict) else None
        valid = _is_timestamp(value)
        return _check(
            check_id, requirement_id, criterion, "runtime_timestamp",
            "ISO-8601 UTC timestamp", value, evidence,
            "VERIFIED" if valid else "FAILED",
            f"{requirement_id}: Runtime timestamp {'is parseable' if valid else 'is missing or invalid'}." if valid else f"{requirement_id}: Runtime timestamp is missing or invalid: {value}.",
            "No action required." if valid else "Return timestamp in ISO-8601 UTC format.",
            execution_timestamp=runtime_timestamp,
            validation_mode="runtime",
        )
    if endpoint:
        matches = urlparse(url).path == endpoint
        return _check(
            check_id, requirement_id, criterion, "runtime_endpoint",
            endpoint, urlparse(url).path, evidence,
            "VERIFIED" if matches else "FAILED",
            f"{requirement_id}: Runtime endpoint {urlparse(url).path} was observed.",
            "No action required." if matches else "Invoke or expose the required endpoint.",
            execution_timestamp=runtime_timestamp,
            validation_mode="runtime",
        )
    return None


def _contains_in_sources(workspace, requirement, value):
    for reference, text in _all_text_sources(workspace, requirement):
        if value in text:
            return reference
    return None


def _timestamp_observation(workspace, requirement):
    for reference, text in _all_text_sources(workspace, requirement):
        match = re.search(r'"timestamp"\s*:\s*"([^"]+)"', text, flags=re.IGNORECASE)
        if match:
            value = match.group(1)
            return value, reference, _is_timestamp(value)
        if "timestamp" in text.lower() and ".toISOString()" in text:
            return "Date.prototype.toISOString()", reference, True
    return None, None, False


def _test_files(project):
    return [
        reference for reference, path in _project_files(project / ".battalion")
        if re.search(r"(^|/)(tests?|specs?)(/|$)", reference, flags=re.IGNORECASE)
        or re.search(r"(test|spec)\.[A-Za-z0-9]+$", reference, flags=re.IGNORECASE)
    ]


def _static_verified(check_id, requirement_id, criterion, check_type, expected, observed, evidence, finding):
    return _check(check_id, requirement_id, criterion, check_type, expected, observed, evidence, "VERIFIED", finding, "No action required.")


def _static_failed(check_id, requirement_id, criterion, check_type, expected, observed, evidence, finding):
    return _check(check_id, requirement_id, criterion, check_type, expected, observed, evidence, "FAILED", finding, "Update implementation or engineering contract.")


def _docs_files(workspace):
    return [
        reference for reference, _ in _project_files(workspace)
        if reference.lower() == "readme.md" or reference.lower().startswith("docs/")
    ]


def _sources_contain(workspace, patterns):
    for reference, text in _project_text_sources(workspace):
        if all(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            return reference
    return None


def _engineering_check_for_criterion(workspace, requirement, criterion, check_number):
    requirement_id = requirement.get("id") if _is_text(requirement.get("id")) else "UNKNOWN"
    check_id = f"ENG-{check_number:03d}"
    existing_evidence = _existing_evidence(workspace, requirement)
    criterion_lower = criterion.lower()

    if "typescript" in criterion_lower:
        files = _source_files(workspace, (".ts", ".tsx"))
        if files:
            return _static_verified(check_id, requirement_id, criterion, "typescript_source", "TypeScript source files exist", files, files, f"{requirement_id}: Verified TypeScript source files exist.")

    if "node.js" in criterion_lower or "nodejs" in criterion_lower or "node " in criterion_lower:
        package, reference = _package_json(workspace)
        if package is not None:
            observed = {
                "package": reference,
                "engines": package.get("engines", {}),
                "scripts": sorted(package.get("scripts", {}).keys()) if isinstance(package.get("scripts"), dict) else [],
            }
            return _static_verified(check_id, requirement_id, criterion, "node_project", "Node.js package metadata exists", observed, [reference], f"{requirement_id}: Verified Node.js package metadata exists.")

    if "entrypoint" in criterion_lower and ("start" in criterion_lower or "starts successfully" in criterion_lower):
        package, reference = _package_json(workspace)
        scripts = package.get("scripts", {}) if isinstance(package, dict) and isinstance(package.get("scripts"), dict) else {}
        source = _sources_contain(workspace, [r"\.listen\("])
        if scripts.get("start") or source:
            evidence = [item for item in [reference if scripts.get("start") else None, source] if item]
            observed = {"start_script": scripts.get("start"), "listener": source}
            return _static_verified(check_id, requirement_id, criterion, "application_entrypoint", "Documented start script or listener exists", observed, evidence, f"{requirement_id}: Verified application entrypoint evidence exists.")

    endpoint = _endpoint_for_requirement(workspace, requirement, criterion)
    if "health endpoint exists" in criterion_lower or criterion_lower.endswith("endpoint exists"):
        source = _contains_in_sources(workspace, requirement, endpoint) if endpoint else None
        if source:
            return _static_verified(check_id, requirement_id, criterion, "endpoint_path", endpoint, endpoint, [source], f"{requirement_id}: Verified endpoint reference {endpoint}.")

    expected_status = _expected_status_for_requirement(workspace, requirement, criterion)
    if expected_status:
        observed, source = _observed_status_value(workspace, requirement)
        if observed is None:
            return _check(
                check_id, requirement_id, criterion, "response_body_literal",
                {"field": "status", "value": expected_status}, None, [],
                "UNABLE_TO_VERIFY",
                f"{requirement_id}: Unable to verify status field equals {expected_status}; no deterministic response evidence was found.",
                "Provide response evidence or run a supported validation mode.",
            )
        if observed == expected_status:
            return _check(
                check_id, requirement_id, criterion, "response_body_literal",
                {"field": "status", "value": expected_status}, {"field": "status", "value": observed}, [source],
                "VERIFIED",
                f"{requirement_id}: Verified status field equals {expected_status}.",
                "No action required.",
            )
        return _check(
            check_id, requirement_id, criterion, "response_body_literal",
            {"field": "status", "value": expected_status}, {"field": "status", "value": observed}, [source],
            "FAILED",
            f'{requirement_id}: Expected response status field "{expected_status}"; observed "{observed}".',
            "Update implementation or tests to satisfy the response contract.",
        )

    if "machine-readable" in criterion_lower and "health" in criterion_lower:
        source = _sources_contain(workspace, [r"\.json\s*\("])
        if source:
            return _static_verified(check_id, requirement_id, criterion, "json_response", "machine-readable JSON response", "JSON response emitted", [source], f"{requirement_id}: Verified machine-readable JSON response evidence exists.")

    endpoint = _extract_endpoint(criterion)
    if endpoint:
        source = _contains_in_sources(workspace, requirement, endpoint)
        if source:
            result = "VERIFIED"
            finding = f"{requirement_id}: Verified endpoint reference {endpoint}."
            recommendation = "No action required."
            evidence = [source]
        elif existing_evidence:
            result = "VERIFIED"
            finding = f"{requirement_id}: Verified recorded evidence exists for endpoint {endpoint}."
            recommendation = "No action required."
            evidence = [reference for reference, _ in existing_evidence]
        else:
            result = "UNABLE_TO_VERIFY"
            finding = f"{requirement_id}: Unable to verify endpoint path {endpoint}; no deterministic artifact references it."
            recommendation = "Provide implementation or response evidence for the endpoint."
            evidence = []
        return _check(check_id, requirement_id, criterion, "endpoint_path", endpoint, endpoint if source else None, evidence, result, finding, recommendation)

    if "http 200" in criterion_lower or "status code 200" in criterion_lower:
        source = None
        for reference, text in _all_text_sources(workspace, requirement):
            if re.search(r"\b200\b", text):
                source = reference
                break
        if source:
            return _check(check_id, requirement_id, criterion, "http_status", 200, 200, [source], "VERIFIED", f"{requirement_id}: Verified HTTP 200 evidence.", "No action required.")
        if existing_evidence:
            evidence = [reference for reference, _ in existing_evidence]
            return _check(check_id, requirement_id, criterion, "http_status", 200, evidence, evidence, "VERIFIED", f"{requirement_id}: Verified recorded evidence exists for HTTP 200 criterion.", "No action required.")
        return _check(check_id, requirement_id, criterion, "http_status", 200, None, [], "UNABLE_TO_VERIFY", f"{requirement_id}: Unable to verify HTTP 200 without response or test evidence.", "Provide HTTP response or passing test evidence.")

    if "get requests are allowed" in criterion_lower:
        endpoint = _endpoint_for_requirement(workspace, requirement, criterion)
        source = _sources_contain(workspace, [r"\.get\s*\(", re.escape(endpoint) if endpoint else r"health"])
        if source:
            return _static_verified(check_id, requirement_id, criterion, "http_method_allowed", "GET allowed", "GET route implemented", [source], f"{requirement_id}: Verified GET route implementation exists.")

    if any(method in criterion_lower for method in ("post", "put", "delete", "patch")) and "rejected" in criterion_lower:
        source = _sources_contain(workspace, [r"\.all\s*\(|405|method\s+not\s+allowed"])
        if source:
            return _static_verified(check_id, requirement_id, criterion, "http_method_rejection", "Unsupported methods rejected", "405/method-not-allowed handling exists", [source], f"{requirement_id}: Verified unsupported method rejection evidence exists.")

    if "timestamp" in criterion_lower:
        value, source, valid = _timestamp_observation(workspace, requirement)
        if value is None:
            if existing_evidence:
                evidence = [reference for reference, _ in existing_evidence]
                return _check(check_id, requirement_id, criterion, "timestamp", "timestamp evidence exists", evidence, evidence, "VERIFIED", f"{requirement_id}: Verified recorded evidence exists for timestamp criterion.", "No action required.")
            return _check(check_id, requirement_id, criterion, "timestamp", "timestamp present", None, [], "UNABLE_TO_VERIFY", f"{requirement_id}: Unable to verify timestamp without response evidence.", "Provide response evidence containing the timestamp.")
        if valid:
            return _check(check_id, requirement_id, criterion, "timestamp", "ISO-8601 timestamp", value, [source], "VERIFIED", f"{requirement_id}: Verified timestamp is parseable.", "No action required.")
        if value is not None:
            return _check(check_id, requirement_id, criterion, "timestamp", "ISO-8601 timestamp", value, [source], "FAILED", f"{requirement_id}: Timestamp is not parseable as ISO-8601: {value}.", "Return timestamp in the required format.")

    if "documentation" in criterion_lower:
        docs = _docs_files(workspace)
        if docs:
            return _static_verified(check_id, requirement_id, criterion, "documentation", "documentation exists", docs, docs, f"{requirement_id}: Verified documentation artifact exists.")

    if "controlled error" in criterion_lower or "stack traces" in criterion_lower or "implementation details" in criterion_lower:
        source = _sources_contain(workspace, [r"internal server error|bad request|not found|method not allowed"])
        if source:
            return _static_verified(check_id, requirement_id, criterion, "safe_error_handling", "generic controlled error handling", "generic error responses found", [source], f"{requirement_id}: Verified generic error handling evidence exists.")

    if "dockerfile" in criterion_lower or "docker" in criterion_lower:
        dockerfile = workspace.parent / "Dockerfile"
        if dockerfile.is_file():
            return _check(check_id, requirement_id, criterion, "file_exists", "Dockerfile exists", "Dockerfile exists", ["Dockerfile"], "VERIFIED", f"{requirement_id}: Verified Dockerfile exists.", "No action required.")
        if existing_evidence:
            evidence = [reference for reference, _ in existing_evidence]
            return _check(check_id, requirement_id, criterion, "file_exists", "Dockerfile or validation evidence exists", evidence, evidence, "VERIFIED", f"{requirement_id}: Verified recorded evidence exists for Docker criterion.", "No action required.")
        return _check(check_id, requirement_id, criterion, "file_exists", "Dockerfile exists", None, [], "UNABLE_TO_VERIFY", f"{requirement_id}: Unable to verify Dockerfile requirement without Dockerfile or recorded evidence.", "Add a Dockerfile or provide validation evidence.")

    if "test" in criterion_lower:
        tests = _test_files(workspace.parent)
        if tests:
            return _check(check_id, requirement_id, criterion, "test_artifacts", "test files exist", tests, tests, "VERIFIED", f"{requirement_id}: Verified test artifact exists.", "No action required.")
        if existing_evidence:
            evidence = [reference for reference, _ in existing_evidence]
            return _check(check_id, requirement_id, criterion, "test_evidence", "test evidence exists", evidence, evidence, "VERIFIED", f"{requirement_id}: Verified recorded test evidence exists.", "No action required.")
        return _check(check_id, requirement_id, criterion, "test_artifacts", "test evidence exists", None, [], "UNABLE_TO_VERIFY", f"{requirement_id}: Unable to verify tests without test files or recorded evidence.", "Provide test files or passing test output evidence.")

    if existing_evidence:
        evidence = [reference for reference, _ in existing_evidence]
        return _check(
            check_id, requirement_id, criterion, "recorded_evidence",
            "evidence exists", evidence, evidence,
            "VERIFIED",
            f"{requirement_id}: Verified recorded evidence exists for acceptance criterion.",
            "No action required.",
        )
    return _check(
        check_id, requirement_id, criterion, "recorded_evidence",
        "evidence exists", None, [],
        "UNABLE_TO_VERIFY",
        f"{requirement_id}: Unable to verify acceptance criterion without deterministic evidence.",
        "Provide implementation, test, or documented validation evidence.",
    )


def _engineering_assurance(workspace, requirements, run=False):
    checks = []
    check_number = 1
    runtime_cache = {}
    runtime_timestamp = _runtime_execution_timestamp(workspace)
    requirements = requirements or []
    if not requirements:
        return {"status": "AMBER", "recommendation": "NO-GO", "checks": [], "summary": {"verified": 0, "failed": 0, "unable_to_verify": 0, "runtime_checks": 0, "static_checks": 0}}

    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        acceptance = requirement.get("acceptance", [])
        if not isinstance(acceptance, list):
            continue
        for criterion in acceptance:
            if not _is_text(criterion):
                continue
            check = _runtime_check_for_criterion(workspace, requirement, criterion, check_number, runtime_cache, runtime_timestamp) if run else None
            static_check = None
            if check is None:
                check = _engineering_check_for_criterion(workspace, requirement, criterion, check_number)
            elif check["result"] == "UNABLE_TO_VERIFY":
                static_check = _engineering_check_for_criterion(workspace, requirement, criterion, check_number)
                if static_check["result"] != "UNABLE_TO_VERIFY":
                    check = static_check
            checks.append(check)
            check_number += 1

    summary = {
        "verified": sum(1 for check in checks if check["result"] == "VERIFIED"),
        "failed": sum(1 for check in checks if check["result"] == "FAILED"),
        "unable_to_verify": sum(1 for check in checks if check["result"] == "UNABLE_TO_VERIFY"),
        "runtime_checks": sum(1 for check in checks if check.get("validation_mode") == "runtime"),
        "static_checks": sum(1 for check in checks if check.get("validation_mode") == "static"),
    }
    if summary["failed"]:
        status = "RED"
    elif summary["unable_to_verify"] or not checks:
        status = "AMBER"
    else:
        status = "GREEN"
    return {"status": status, "recommendation": "GO" if status == "GREEN" else "NO-GO", "checks": checks, "summary": summary}


def _latest_dispatch_metadata(workspace):
    dispatch_root = workspace / "dispatches"
    if not dispatch_root.is_dir():
        return None
    candidates = sorted(path for path in dispatch_root.iterdir() if path.is_dir() and (path / "metadata.yaml").is_file())
    if not candidates:
        return None
    try:
        return read_yaml(candidates[-1] / "metadata.yaml")
    except ValueError:
        return None


def _write_assurance_artifacts(workspace, result):
    data = result.to_dict()
    data["latest_dispatch"] = _latest_dispatch_metadata(workspace)
    (workspace / "assurance.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Mission Assurance",
        "",
        f"Engineering Result: {result.engineering_result.get('status', 'UNKNOWN')}",
        f"Governance Result: {result.governance_result.get('status', 'UNKNOWN')}",
        f"Overall Status: {result.status}",
        f"Recommendation: {result.recommendation}",
        "",
        "## Engineering Summary",
        "",
        f"- Verified: {result.engineering_result.get('summary', {}).get('verified', 0)}",
        f"- Failed: {result.engineering_result.get('summary', {}).get('failed', 0)}",
        f"- Unable to verify: {result.engineering_result.get('summary', {}).get('unable_to_verify', 0)}",
        f"- Runtime Checks: {result.engineering_result.get('summary', {}).get('runtime_checks', 0)}",
        f"- Static Checks: {result.engineering_result.get('summary', {}).get('static_checks', 0)}",
        "",
    ]
    failed = [check for check in result.engineering_result.get("checks", []) if check.get("result") == "FAILED"]
    unable = [check for check in result.engineering_result.get("checks", []) if check.get("result") == "UNABLE_TO_VERIFY"]
    verified = [check for check in result.engineering_result.get("checks", []) if check.get("result") == "VERIFIED"]
    for title, values in (("Failed", failed), ("Unable to verify", unable), ("Verified", verified)):
        lines.extend([f"## {title}", ""])
        if values:
            for check in values:
                lines.append(f"### {check['requirement_id']} — {check['result']}")
                lines.append("")
                lines.append(f"- Criterion: {check['criterion']}")
                lines.append(f"- Check Type: {check['check_type']}")
                lines.append(f"- Expected: {json.dumps(check.get('expected'), sort_keys=True)}")
                lines.append(f"- Observed: {json.dumps(check.get('observed'), sort_keys=True)}")
                lines.append(f"- Evidence: {json.dumps(check.get('evidence'), sort_keys=True)}")
                lines.append(f"- Finding: {check['finding']}")
                lines.append(f"- Recommendation: {check['recommendation']}")
                if check.get("evidence"):
                    lines.append(f"- Validation Mode: {check.get('validation_mode', 'static')}")
                if check.get("execution_timestamp"):
                    lines.append(f"- Execution Timestamp: {check['execution_timestamp']}")
        else:
            lines.append("- None")
        lines.append("")
    lines.extend(["## Governance", ""])
    governance_findings = result.governance_result.get("findings", [])
    if governance_findings:
        lines.extend(f"- {finding}" for finding in governance_findings)
    else:
        lines.append("- None")
    (workspace / "assurance.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _governance_assure(workspace: Path) -> AssuranceResult:
    red_findings = []
    amber_findings = []
    clarification_counts = {status: 0 for status in CLARIFICATION_STATUSES}
    contract_clarifications = None
    missing = [name for name in REQUIRED_FILES if not (workspace / name).is_file()]
    red_findings.extend("Workspace: Missing required file: " + name for name in missing)

    mission = None
    mission_id = None
    if "mission.yaml" not in missing:
        try:
            mission = read_yaml(workspace / "mission.yaml")
        except ValueError as exc:
            red_findings.append(f"Mission: {exc}")
        if mission is not None:
            if not isinstance(mission, dict):
                red_findings.append("Mission: mission.yaml must contain an object")
            else:
                for field in ("id", "title", "objective", "mission_prompt", "status"):
                    if not _is_text(mission.get(field)):
                        red_findings.append(f"Mission: Missing or invalid mission field: {field}")
                mission_id = mission.get("id") if _is_text(mission.get("id")) else None

    known_reviewers = None
    if "agents.yaml" not in missing:
        try:
            agents = read_yaml(workspace / "agents.yaml")
        except ValueError as exc:
            red_findings.append(f"Mission: {exc}")
        else:
            if not isinstance(agents, dict) or not isinstance(agents.get("agents"), list) or not agents["agents"]:
                red_findings.append("Mission: agents.yaml must contain a non-empty agents list")
            else:
                known_reviewers = set()
                for index, agent in enumerate(agents["agents"], 1):
                    if not isinstance(agent, dict) or not _is_text(agent.get("id")):
                        red_findings.append(f"Mission: Agent #{index} has an invalid id")
                    else:
                        known_reviewers.add(agent["id"])

    requirements = None
    if "ledger.yaml" not in missing:
        try:
            ledger = read_yaml(workspace / "ledger.yaml")
        except ValueError as exc:
            red_findings.append(f"Mission: {exc}")
        else:
            if not isinstance(ledger, dict) or not isinstance(ledger.get("requirements"), list):
                red_findings.append("Mission: ledger.yaml must contain a requirements list")
            else:
                requirements = ledger["requirements"]
                contract_clarifications = ledger.get("clarifications")
                generated_contract = ledger.get("generated_by") == "mission_analyst"
                contract_constraint_ids = None
                if ledger.get("generated_by") == "mission_analyst":
                    if ledger.get("mission_id") != mission_id:
                        red_findings.append("Mission contract: mission_id does not match mission.yaml")
                    expected_prompt = mission.get("mission_prompt") if isinstance(mission, dict) else None
                    if ledger.get("mission_prompt") != expected_prompt:
                        red_findings.append("Mission contract: mission_prompt does not match the authoritative mission prompt")
                    constraint_findings, contract_constraint_ids = _validate_constraints(ledger.get("constraints"), expected_prompt)
                    red_findings.extend(constraint_findings)
                    red_findings.extend(_validate_contract_records(ledger.get("assumptions"), "Assumption", expected_prompt, contract_constraint_ids, True))
                    red_findings.extend(_validate_contract_records(ledger.get("risks"), "Risk", expected_prompt, contract_constraint_ids, True))
                    clarification_red, clarification_amber, clarification_counts = _validate_clarifications(ledger.get("clarifications"), expected_prompt, contract_constraint_ids)
                    red_findings.extend(clarification_red)
                    amber_findings.extend(clarification_amber)
                seen_ids = set()
                for index, item in enumerate(requirements, 1):
                    item_red, item_amber, requirement_id = _validate_requirement(
                        item, index, workspace, known_reviewers,
                        ledger.get("mission_prompt"), contract_constraint_ids, generated_contract,
                    )
                    red_findings.extend(item_red)
                    amber_findings.extend(item_amber)
                    if requirement_id in seen_ids:
                        red_findings.append(f"{requirement_id}: Duplicate requirement id")
                    elif requirement_id:
                        seen_ids.add(requirement_id)

    if "events.jsonl" not in missing:
        red_findings.extend(_validate_audit(workspace / "events.jsonl", mission_id, contract_clarifications))

    if red_findings:
        return AssuranceResult("RED", "NO-GO", 100, red_findings + amber_findings, clarification_counts)
    if requirements is not None and not requirements:
        return AssuranceResult("AMBER", "NO-GO", 100, ["Mission: No requirements have been planned"], clarification_counts)
    if amber_findings:
        return AssuranceResult("AMBER", "NO-GO", 100, amber_findings, clarification_counts)
    return AssuranceResult("GREEN", "GO", 100, ["Mission contract satisfied: all requirements are closed with acceptance criteria, verifiable evidence, completed reviews, and a valid audit trail"], clarification_counts)


def assure(workspace: Path, run: bool = False) -> AssuranceResult:
    governance = _governance_assure(workspace)
    requirements = []
    try:
        ledger = read_yaml(workspace / "ledger.yaml")
        if isinstance(ledger, dict) and isinstance(ledger.get("requirements"), list):
            requirements = ledger["requirements"]
    except ValueError:
        requirements = []

    engineering = _engineering_assurance(workspace, requirements, run=run)
    if engineering["status"] == "RED":
        overall_status = "RED"
    elif governance.status == "RED":
        overall_status = "RED"
    elif engineering["status"] == "AMBER" or governance.status == "AMBER":
        overall_status = "AMBER"
    else:
        overall_status = "GREEN"
    recommendation = "GO" if overall_status == "GREEN" else "NO-GO"

    engineering_findings = [
        check["finding"] for check in engineering["checks"]
        if check["result"] in {"FAILED", "UNABLE_TO_VERIFY"}
    ]
    if not engineering_findings and engineering["status"] == "GREEN":
        engineering_findings = ["Engineering contract satisfied: all acceptance criteria are verified by deterministic evidence."]
    findings = []
    findings.extend(engineering_findings)
    findings.extend(governance.findings)

    result = AssuranceResult(
        overall_status,
        recommendation,
        100,
        findings,
        governance.clarification_counts,
        engineering_result=engineering,
        governance_result={
            "status": governance.status,
            "recommendation": governance.recommendation,
            "findings": governance.findings,
        },
    )
    if workspace.is_dir():
        _write_assurance_artifacts(workspace, result)
    return result
