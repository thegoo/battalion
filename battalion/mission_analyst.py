"""Deterministic constraint extraction and mission-contract generation."""

import re
from typing import Any, Dict, List, Sequence


FRAMEWORK_TERMS = ("express", "fastapi", "flask", "django", "nestjs", "koa", "hapi", "spring", "asp.net")
DEPLOYMENT_TERMS = ("production", "aws", "azure", "gcp", "cloud", "kubernetes", "serverless", "hosting")
SECURITY_TERMS = ("auth", "login", "password", "token", "jwt", "security", "permission", "secret", "encrypt", "identity")


def _matches(prompt: str, pattern: str) -> bool:
    return re.search(pattern, prompt, flags=re.IGNORECASE) is not None


def _excerpt(prompt: str, patterns: Sequence[str]) -> str:
    statements = [part.strip() for part in re.split(r"(?<=[.!?])\s+", prompt) if part.strip()]
    for statement in statements:
        if any(_matches(statement, pattern) for pattern in patterns):
            return statement
    return prompt.strip()


def _trace(prompt_excerpt: str, rationale: str, constraint_ids: Sequence[str]) -> Dict[str, Any]:
    return {
        "source": "mission_prompt",
        "prompt_excerpt": prompt_excerpt,
        "rationale": rationale,
        "constraint_ids": list(constraint_ids),
    }


def extract_constraints(prompt: str) -> Dict[str, List[Dict[str, str]]]:
    constraints = {category: [] for category in ("functional", "technical", "security", "testing", "operational")}
    counters = {"functional": "FC", "technical": "TC", "security": "SC", "testing": "TEST", "operational": "OC"}

    def add(category: str, statement: str, patterns: Sequence[str]) -> None:
        if any(item["statement"] == statement for item in constraints[category]):
            return
        identifier = f"{counters[category]}-{len(constraints[category]) + 1:03d}"
        constraints[category].append({
            "id": identifier,
            "statement": statement,
            "prompt_excerpt": _excerpt(prompt, patterns),
        })

    if _matches(prompt, r"\bhealth(?:[- ]check)?\s+endpoint\b|\bhealth\s+check\b"):
        add("functional", "A health endpoint is required.", (r"health",))
    elif _matches(prompt, r"\b(?:rest\s+)?api\b|\bendpoint\b"):
        add("functional", "API behavior is required.", (r"\bapi\b", r"endpoint"))
    if _matches(prompt, r"\bhttp\s*200\b|\bstatus\s*(?:code\s*)?200\b"):
        add("functional", "Successful requests must return HTTP 200.", (r"200",))
    if _matches(prompt, r"\btimestamp\b"):
        add("functional", "The response must include a timestamp.", (r"timestamp",))

    if _matches(prompt, r"\btypescript\b"):
        add("technical", "TypeScript is required.", (r"typescript",))
    if _matches(prompt, r"\bnode(?:\.js|js)?\b"):
        add("technical", "Node.js is required.", (r"\bnode",))
    if _matches(prompt, r"\bdocker\b|\bcontaineri[sz]ed?\b"):
        add("technical", "Docker packaging is required.", (r"docker", r"container"))

    if _matches(prompt, r"\bget[- ]only\b|\bonly\s+(?:allow\s+)?get\b|\ballow\s+get(?:\s+requests?)?\s+only\b"):
        add("security", "Only GET requests are permitted.", (r"get",))
    if _matches(prompt, r"\bowasp\b"):
        add("security", "Error handling must follow OWASP guidance.", (r"owasp",))
    if _matches(prompt, r"(?:no|without|prevent)\s+(?:sensitive\s+)?information disclosure|do not disclose"):
        add("security", "Responses must not disclose sensitive implementation information.", (r"disclos",))
    if _matches(prompt, r"malformed\s+requests?"):
        add("security", "Malformed requests must be handled safely.", (r"malformed",))

    if _matches(prompt, r"happy[- ]path"):
        add("testing", "Happy-path tests are required.", (r"happy[- ]path",))
    if _matches(prompt, r"negative[- ]path"):
        add("testing", "Negative-path tests are required.", (r"negative[- ]path",))
    if _matches(prompt, r"malicious[- ]request"):
        add("testing", "Malicious-request tests are required.", (r"malicious[- ]request",))

    if _matches(prompt, r"\bdocker\b|\bcontaineri[sz]ed?\b"):
        add("operational", "The application must run in a container.", (r"docker", r"container"))
    if _matches(prompt, r"\blocal(?:ly)?\b"):
        add("operational", "Local execution is required.", (r"local",))
    if _matches(prompt, r"startup instructions?|run instructions?"):
        add("operational", "Startup instructions are required.", (r"instructions?",))
    return constraints


def _review(reviewer: str, reason: str) -> Dict[str, str]:
    return {"reviewer": reviewer, "status": "pending", "reason": reason}


def _requirement(
    identifier: str,
    statement: str,
    acceptance: List[str],
    reviews: List[Dict[str, str]],
    owner: str,
    traceability: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "id": identifier,
        "statement": statement,
        "status": "proposed",
        "owner": owner,
        "acceptance": acceptance,
        "evidence": [],
        "assumptions": [],
        "risks": [],
        "required_reviews": reviews,
        "traceability": traceability,
    }


def _items(constraints, category, text):
    return [item for item in constraints[category] if text.lower() in item["statement"].lower()]


def _ids(items):
    return [item["id"] for item in items]


def _source(items, prompt):
    return items[0]["prompt_excerpt"] if items else prompt


def _clarifications(prompt: str, constraints) -> List[Dict[str, Any]]:
    questions = []
    has_endpoint = bool(constraints["functional"])
    has_path = _matches(prompt, r"(?:path|route)(?:\s+is|\s+at|:)?\s*[`'\"]?/[a-z0-9_/{}/.-]+|(?:^|\s)/[a-z0-9_/{}/.-]+")
    has_framework = any(term in prompt.lower() for term in FRAMEWORK_TERMS)
    health_items = _items(constraints, "functional", "health endpoint")

    def add(question: str, excerpt: str, rationale: str, constraint_ids: Sequence[str]) -> None:
        questions.append({
            "id": f"Q-{len(questions) + 1:03d}",
            "question": question,
            "status": "open",
            "traceability": _trace(excerpt, rationale, constraint_ids),
        })

    if has_endpoint and not has_path:
        endpoint_items = constraints["functional"][:1]
        add("What endpoint path should be used?", _source(endpoint_items, prompt), "The prompt requires an endpoint but does not specify its path.", _ids(endpoint_items))
    if has_endpoint and not has_framework:
        endpoint_items = constraints["functional"][:1]
        add("What application framework should be used?", _source(endpoint_items, prompt), "The prompt requires API behavior but does not select a framework.", _ids(endpoint_items))
    if health_items and not _matches(prompt, r"timestamp\s+(?:format|as)|iso[- ]?8601|unix\s+(?:time|epoch)|rfc\s*3339"):
        add("What timestamp format should be returned?", _source(health_items, prompt), "The health response contract does not define a timestamp format.", _ids(health_items))
    owasp_items = _items(constraints, "security", "OWASP")
    if owasp_items and not _matches(prompt, r"owasp\s+(?:asvs|top\s*10|api\s+security|\d{4}|v\d)"):
        add("Which OWASP standard or version should govern error handling?", _source(owasp_items, prompt), "OWASP guidance is required but its control baseline is not specified.", _ids(owasp_items))
    return questions


def generate_mission_contract(mission_id: str, prompt: str) -> Dict[str, Any]:
    """Convert an immutable mission prompt into a traceable initial contract."""
    constraints = extract_constraints(prompt)
    requirements = []

    def append(statement, acceptance, reviews, owner, items, rationale):
        requirements.append(_requirement(
            f"R-{len(requirements) + 1:03d}", statement, acceptance, reviews, owner,
            _trace(_source(items, prompt), rationale, _ids(items)),
        ))

    typescript = _items(constraints, "technical", "TypeScript")
    node = _items(constraints, "technical", "Node.js")
    stack_items = typescript + node
    if stack_items:
        technologies = " ".join(name for name, present in (("TypeScript", typescript), ("Node", node)) if present)
        append(
            f"Create {technologies} application",
            [
                *( ["Application source is implemented in TypeScript"] if typescript else [] ),
                *( ["The application executes on Node.js"] if node else [] ),
                "A documented application entrypoint starts successfully",
            ],
            [_review("architect", "Validate the required technology stack, application boundary, and entrypoint design.")],
            "developer", stack_items, "The prompt explicitly selects the application technology stack.",
        )
    else:
        append(
            "Create application entrypoint",
            ["An application entrypoint exists", "The application can be started locally", "Startup instructions identify the executable entrypoint"],
            [_review("architect", "Validate the application boundary, structure, and entrypoint design.")],
            "developer", [], "An executable entrypoint is necessary to deliver the behavior described by the prompt.",
        )

    health = _items(constraints, "functional", "health endpoint")
    functional = constraints["functional"]
    if health:
        acceptance = ["A health endpoint exists", "A valid GET request returns HTTP 200", "The response provides a machine-readable health result"]
        if _items(constraints, "functional", "timestamp"):
            acceptance.append("The response includes a timestamp in the clarified format")
        append(
            "Implement health endpoint", acceptance,
            [_review("architect", "Validate the endpoint contract and service boundary."), _review("tester", "Validate health responses against the prompt-derived criteria.")],
            "developer", health + _items(constraints, "functional", "HTTP 200"), "The prompt explicitly requires health endpoint behavior.",
        )
    elif functional:
        append(
            "Implement the requested API behavior",
            ["The requested endpoint or endpoints exist", "Valid requests return successful responses", "Responses represent the behavior described by the mission prompt"],
            [_review("architect", "Validate the API contract and design boundaries."), _review("tester", "Validate the requested behavior with evidence.")],
            "developer", functional, "The prompt explicitly requires API behavior.",
        )
    else:
        append(
            "Implement the requested mission behavior",
            ["The behavior described by the mission prompt is implemented", "The primary success path produces an observable expected result", "Invalid or unsupported input fails clearly"],
            [_review("architect", "Validate alignment with mission boundaries."), _review("tester", "Validate the requested behavior with evidence.")],
            "developer", [], "This requirement implements the primary behavior stated in the mission prompt.",
        )

    docker = _items(constraints, "technical", "Docker") + _items(constraints, "operational", "container")
    if docker:
        append(
            "Containerize application with Docker",
            ["A Dockerfile defines the application image", "The container image builds successfully", "The application starts and is reachable when the container runs"],
            [_review("architect", "Validate container boundaries and packaging design."), _review("devops", "Validate image build and runtime instructions."), _review("sre", "Validate container startup and operational readiness.")],
            "developer", docker, "The prompt explicitly requires Docker packaging and container execution.",
        )

    get_only = _items(constraints, "security", "Only GET")
    if get_only:
        append(
            "Enforce GET-only endpoint behavior",
            ["GET requests are allowed for the endpoint", "POST requests are rejected", "PUT requests are rejected", "DELETE and PATCH requests are rejected"],
            [_review("architect", "Validate that HTTP method restrictions match the API contract."), _review("secops", "Validate method restriction enforcement and bypass resistance."), _review("tester", "Test allowed and rejected HTTP methods.")],
            "developer", get_only, "The prompt explicitly restricts allowed HTTP methods to GET.",
        )

    owasp = _items(constraints, "security", "OWASP")
    disclosure = _items(constraints, "security", "disclose")
    malformed = _items(constraints, "security", "Malformed")
    security_items = owasp + disclosure + malformed
    if security_items or any(term in prompt.lower() for term in SECURITY_TERMS):
        append(
            "Implement secure error handling",
            ["Malformed requests receive controlled error responses", "Error responses do not expose stack traces, secrets, or implementation details", "Security-relevant failures are handled consistently with the clarified OWASP baseline"],
            [_review("secops", "Assess OWASP alignment, information disclosure, and malformed-request handling."), _review("tester", "Validate safe behavior for invalid and malicious requests.")],
            "developer", security_items, "The prompt explicitly requires security guidance or security-sensitive behavior.",
        )

    testing_items = constraints["testing"]
    test_acceptance = []
    if _items(constraints, "testing", "Happy-path"):
        test_acceptance.append("Happy-path tests validate successful requests")
    if _items(constraints, "testing", "Negative-path"):
        test_acceptance.append("Negative-path tests validate invalid or unsupported requests")
    if _items(constraints, "testing", "Malicious-request"):
        test_acceptance.append("Malicious-request tests validate safe rejection without information disclosure")
    if not test_acceptance:
        test_acceptance.extend(["Automated tests cover the primary mission behavior", "At least one negative or failure path is tested"])
    test_acceptance.append("The test suite can be run locally")
    test_reviews = [_review("tester", "Validate prompt-required test scenarios, coverage, and reproducibility.")]
    if _items(constraints, "testing", "Malicious-request"):
        test_reviews.append(_review("secops", "Validate that malicious-request tests exercise relevant abuse cases."))
    append(
        "Create automated tests", test_acceptance, test_reviews, "tester", testing_items,
        "The prompt explicitly names test scenarios." if testing_items else "Tests provide evidence that the prompt-described behavior is satisfied.",
    )

    operational = constraints["operational"]
    append(
        "Create mission documentation",
        ["Documentation explains installation or setup", "Documentation explains how to run the solution", "Documentation maps validation steps to the mission requirements"],
        [_review("tester", "Confirm that documented validation steps are complete and reproducible."), _review("ux", "Review documentation clarity and the user execution flow.")],
        "developer", operational, "Documentation is required to operate and verify the solution described by the prompt.",
    )

    clarifications = _clarifications(prompt, constraints)
    first_excerpt = _source(constraints["technical"] or constraints["functional"], prompt)
    assumptions = [{
        "id": "A-001",
        "statement": "The explicitly named development tools are available in the local validation environment." if constraints["technical"] else "Local filesystem and process execution are available for validation.",
        "traceability": _trace(first_excerpt, "This is a low-risk execution prerequisite and does not select an unspecified framework or interface contract.", _ids(constraints["technical"])),
    }]
    risks = []
    if any("framework" in item["question"].lower() for item in clarifications):
        risks.append({
            "id": f"RISK-{len(risks) + 1:03d}", "statement": "Framework selection remains unresolved.",
            "traceability": _trace(_source(constraints["functional"], prompt), "The prompt requires an endpoint but omits the framework, which may affect design and dependencies.", _ids(constraints["functional"])),
        })
    if not any(term in prompt.lower() for term in DEPLOYMENT_TERMS):
        risks.append({
            "id": f"RISK-{len(risks) + 1:03d}", "statement": "The target deployment environment is not specified.",
            "traceability": _trace(prompt, "The mission describes the solution without identifying its eventual deployment target.", _ids(constraints["operational"])),
        })
    if owasp:
        risks.append({
            "id": f"RISK-{len(risks) + 1:03d}", "statement": "The applicable OWASP standard or version requires clarification.",
            "traceability": _trace(_source(owasp, prompt), "OWASP guidance is explicit but its control baseline is ambiguous.", _ids(owasp)),
        })
    if not risks:
        risks.append({
            "id": "RISK-001", "statement": "Non-functional production constraints may remain unspecified.",
            "traceability": _trace(prompt, "The prompt is authoritative but may not enumerate every production constraint.", []),
        })

    return {
        "mission_id": mission_id,
        "mission_prompt": prompt,
        "generated_by": "mission_analyst",
        "requirements": requirements,
        "constraints": constraints,
        "assumptions": assumptions,
        "risks": risks,
        "clarifications": clarifications,
    }
