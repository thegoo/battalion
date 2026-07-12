"""Deterministic constraint extraction and mission-contract generation."""

import re
from typing import Any, Dict, List, Sequence


FRAMEWORK_TERMS = ("express", "fastify", "fastapi", "flask", "django", "nestjs", "koa", "hapi", "spring", "asp.net")
DEPLOYMENT_TERMS = ("production", "aws", "azure", "gcp", "cloud", "kubernetes", "serverless", "hosting")
SECURITY_TERMS = ("auth", "login", "password", "token", "jwt", "security", "permission", "secret", "encrypt", "identity")
CURRENT_VERSION_PATTERN = r"\b(?:current|latest|latest\s+stable|current\s+supported|current\s+guidance|latest\s+guidance)\b"
EXPLICIT_VERSION_PATTERNS = (
    r"\.NET\s+\d+(?:\.\d+)?",
    r"Node(?:\.js|js)?\s+\d+(?:\.\d+)?",
    r"OWASP(?:\s+API\s+Security)?(?:\s+Top\s*10)?\s+\d{4}",
)


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
    if _matches(prompt, r"\.net\b|\bdotnet\b|\basp\.net\b|\bc#\b"):
        add("technical", ".NET is required.", (r"\.net", r"dotnet", r"asp\.net", r"c#"))
    for version_pattern in EXPLICIT_VERSION_PATTERNS:
        match = re.search(version_pattern, prompt, flags=re.IGNORECASE)
        if match:
            value = prompt[match.start():match.end()]
            add("technical", f"{value} is specified.", (re.escape(value),))
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


def _clarifications(prompt: str, constraints, created_at: str) -> List[Dict[str, Any]]:
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
            "answer": None,
            "created_at": created_at,
            "resolved_at": None,
            "resolved_by": None,
            "traceability": _trace(excerpt, rationale, constraint_ids),
            "history": [{
                "action": "created",
                "status": "open",
                "value": question,
                "actor": "mission_analyst",
                "timestamp": created_at,
            }],
        })

    if has_endpoint and not has_path:
        endpoint_items = constraints["functional"][:1]
        add("What endpoint path should be used?", _source(endpoint_items, prompt), "The prompt requires an endpoint but does not specify its path.", _ids(endpoint_items))
    if has_endpoint and not has_framework:
        endpoint_items = constraints["functional"][:1]
        add("What application framework should be used?", _source(endpoint_items, prompt), "The prompt requires API behavior but does not select a framework.", _ids(endpoint_items))
    if health_items and not _matches(prompt, r"timestamp\s+(?:format|as)|iso[- ]?8601|unix\s+(?:time|epoch)|rfc\s*3339"):
        add("What timestamp format should be returned?", _source(health_items, prompt), "The health response contract does not define a timestamp format.", _ids(health_items))
    return questions


def _technology_constraint_items(constraints: Dict[str, List[Dict[str, str]]]) -> List[Dict[str, str]]:
    return [
        item for category in ("technical", "security", "operational")
        for item in constraints.get(category, [])
        if any(term in item.get("statement", "").lower() for term in (
            "typescript", "node", ".net", "owasp", "docker", "container", "framework", "runtime",
        ))
    ]


def _current_or_versioned_guidance(prompt: str) -> bool:
    return _matches(prompt, CURRENT_VERSION_PATTERN) or any(_matches(prompt, pattern) for pattern in EXPLICIT_VERSION_PATTERNS)


def _append_contract_item(values: List[Dict[str, Any]], prefix: str, statement: str, traceability: Dict[str, Any]) -> None:
    if any(item.get("statement") == statement for item in values):
        return
    values.append({
        "id": f"{prefix}-{len(values) + 1:03d}",
        "statement": statement,
        "traceability": traceability,
    })


def _is_plan_template_mission(prompt: str) -> bool:
    return _matches(prompt, r"\bplan template\b") and _matches(prompt, r"\bmission-plan\.md\b")


def _is_readme_mission(prompt: str) -> bool:
    return _matches(prompt, r"\breadme(?:\.md)?\b")


def _generate_plan_template_contract(mission_id: str, prompt: str) -> Dict[str, Any]:
    constraints = {category: [] for category in ("functional", "technical", "security", "testing", "operational")}
    constraints["functional"] = [
        {
            "id": "FC-001",
            "statement": "Plan Template v1 must render the authoritative mission plan artifact.",
            "prompt_excerpt": _excerpt(prompt, (r"Plan Template v1", r"mission-plan\.md")),
        },
        {
            "id": "FC-002",
            "statement": "The plan must include the required planning sections.",
            "prompt_excerpt": _excerpt(prompt, (r"Mission, Objective, Constraints", r"required section")),
        },
        {
            "id": "FC-003",
            "statement": "The plan must preserve Battalion doctrine boundaries.",
            "prompt_excerpt": _excerpt(prompt, (r"Battalion owns the WHAT", r"humans own decisions")),
        },
    ]
    constraints["testing"] = [
        {
            "id": "TEST-001",
            "statement": "Regression tests must cover the generated Plan Template v1 sections.",
            "prompt_excerpt": _excerpt(prompt, (r"Regression tests", r"deterministic test suite")),
        },
        {
            "id": "TEST-002",
            "statement": "The full deterministic test suite must pass.",
            "prompt_excerpt": _excerpt(prompt, (r"full deterministic test suite",)),
        },
    ]
    constraints["operational"] = [
        {
            "id": "OC-001",
            "statement": "The work must be managed using Battalion's generated plan artifact.",
            "prompt_excerpt": _excerpt(prompt, (r"managed using the Plan Template", r"dogfood")),
        },
        {
            "id": "OC-002",
            "statement": "Commit and pull request work are out of scope unless explicitly authorized.",
            "prompt_excerpt": _excerpt(prompt, (r"Do not commit", r"pull request", r"PR")),
        },
    ]
    requirements = [
        _requirement(
            "R-001",
            "Render Plan Template v1 to .battalion/mission-plan.md",
            [
                "`battalion plan` writes `.battalion/mission-plan.md`.",
                "The generated plan identifies itself as the authoritative execution artifact.",
                "The generated plan remains deterministic Markdown.",
            ],
            [],
            "developer",
            _trace(_source([constraints["functional"][0]], prompt), "The prompt explicitly requires a production-quality Markdown plan artifact.", ["FC-001"]),
        ),
        _requirement(
            "R-002",
            "Include the required Plan Template v1 sections",
            [
                "The generated plan includes Mission, Objective, Constraints, Assumptions, and Risks.",
                "The generated plan includes Traceable Requirements with IDs and acceptance criteria.",
                "The generated plan includes Deliverables, Out of Scope, Execution Strategy, Validation Plan, Human Decisions, and Definition of Complete.",
            ],
            [],
            "developer",
            _trace(_source([constraints["functional"][1]], prompt), "The prompt enumerates the minimum required Plan Template v1 sections.", ["FC-002"]),
        ),
        _requirement(
            "R-003",
            "Encode Battalion doctrine in the plan artifact",
            [
                "The plan states that Battalion owns the WHAT and executors own the HOW.",
                "The plan states that humans own decisions.",
                "The plan states that recommendations are not decisions.",
                "The plan states that Battalion remains boring and builds Battalion using its own artifacts.",
            ],
            [],
            "developer",
            _trace(_source([constraints["functional"][2]], prompt), "The prompt requires the artifact to reinforce Battalion doctrine.", ["FC-003"]),
        ),
        _requirement(
            "R-004",
            "Cover Plan Template v1 with deterministic regression tests",
            [
                "Happy-path tests assert the generated plan includes the required v1 sections.",
                "Negative-path tests assert out-of-scope work is not introduced by this slice.",
                "Tests assert doctrine-critical language is present.",
                "The full deterministic test suite passes.",
            ],
            [],
            "tester",
            _trace(_source(constraints["testing"], prompt), "The prompt requires regression coverage and a passing deterministic test suite.", ["TEST-001", "TEST-002"]),
        ),
        _requirement(
            "R-005",
            "Document the Plan Template v1 surface",
            [
                "README documentation identifies `.battalion/mission-plan.md` as the current Plan Template v1 output.",
                "Template documentation states that no runtime template loader is introduced by this slice.",
                "Documentation preserves the separation between planning signals and human decisions.",
            ],
            [],
            "developer",
            _trace(prompt, "The prompt requires a production-quality artifact and explicit non-goal boundaries.", ["OC-002"]),
        ),
    ]
    assumptions = [{
        "id": "A-001",
        "statement": "The existing deterministic plan renderer is the correct implementation surface for Plan Template v1.",
        "traceability": _trace(_source([constraints["functional"][0]], prompt), "Using the existing renderer keeps the slice boring and avoids a new template loader.", ["FC-001"]),
    }]
    risks = [{
        "id": "RISK-001",
        "statement": "The generated contract for template/documentation work may still be less precise than implementation-focused missions.",
        "traceability": _trace(prompt, "Dogfooding exposed that artifact planning is a first-class product path that needs continued refinement.", []),
    }]
    return {
        "mission_id": mission_id,
        "mission_prompt": prompt,
        "generated_by": "mission_analyst",
        "requirements": requirements,
        "constraints": constraints,
        "assumptions": assumptions,
        "risks": risks,
        "clarifications": [],
    }


def _generate_readme_contract(mission_id: str, prompt: str) -> Dict[str, Any]:
    constraints = {category: [] for category in ("functional", "technical", "security", "testing", "operational")}
    constraints["functional"] = [
        {
            "id": "FC-001",
            "statement": "README.md must satisfy the clarified documentation intent.",
            "prompt_excerpt": _excerpt(prompt, (r"README", r"overview", r"setup", r"install")),
        },
        {
            "id": "FC-002",
            "statement": "README.md must be written for the clarified audience.",
            "prompt_excerpt": _excerpt(prompt, (r"external", r"internal", r"contributor", r"user", r"operator")),
        },
    ]
    constraints["testing"] = [{
        "id": "TEST-001",
        "statement": "Documentation validation must confirm the requested README content exists.",
        "prompt_excerpt": _excerpt(prompt, (r"README", r"overview", r"setup", r"install")),
    }]
    lower = prompt.lower()
    depth = "blank" if "blank" in lower else "detailed" if "detailed" in lower else "lightweight" if "lightweight" in lower else "appropriate"
    audience = "external contributors" if _matches(prompt, r"\bexternal\b") and _matches(prompt, r"\bcontributor") else "the clarified audience"
    content_acceptance = ["README.md exists"]
    if _matches(prompt, r"\boverview\b"):
        content_acceptance.append("README.md provides a project overview")
    if _matches(prompt, r"\bsetup\b|\binstall(?:ation)?\b"):
        content_acceptance.append("README.md includes setup or installation instructions")
    if depth == "lightweight":
        content_acceptance.append("README.md remains lightweight while still useful")
    elif depth == "blank":
        content_acceptance.append("README.md is intentionally blank or minimal for repository initialization")
    elif depth == "detailed":
        content_acceptance.append("README.md includes detailed project documentation")
    requirements = [
        _requirement(
            "R-001",
            "Create contributor-facing README documentation" if "contributor" in audience else "Create README documentation",
            content_acceptance,
            [_review("ux", "Review README clarity and audience fit.")],
            "developer",
            _trace(_source(constraints["functional"], prompt), "The mission requires README documentation with clarified content depth and intent.", ["FC-001"]),
        ),
        _requirement(
            "R-002",
            "Align README content to the intended audience",
            [
                f"README.md is understandable for {audience}",
                "README.md avoids unrelated application, API, data, UI, infrastructure, or integration scope",
            ],
            [_review("ux", "Validate that the README matches the intended reader and does not broaden scope.")],
            "developer",
            _trace(_source([constraints["functional"][1]], prompt), "The human answer identifies who the README is for.", ["FC-002"]),
        ),
        _requirement(
            "R-003",
            "Validate README content",
            [
                "Deterministic validation confirms README.md exists",
                "Validation confirms requested overview and setup content when applicable",
                "Validation fails if README.md introduces unsupported application, API, data, UI, infrastructure, or integration scope",
            ],
            [_review("tester", "Confirm README validation evidence is reproducible.")],
            "tester",
            _trace(_source(constraints["testing"], prompt), "The slice requires evidence that the documentation satisfies the clarified request.", ["TEST-001"]),
        ),
    ]
    assumptions = [{
        "id": "A-001",
        "statement": "No application code changes are required for this README-only mission.",
        "traceability": _trace(_source(constraints["functional"], prompt), "README work is documentation-focused unless the mission explicitly expands scope.", ["FC-001"]),
    }]
    risks = [{
        "id": "RISK-001",
        "statement": "The README may omit project-specific details that are not present in the repository or clarified answers.",
        "traceability": _trace(prompt, "Documentation quality depends on available repository context and human-provided intent.", []),
    }]
    return {
        "mission_id": mission_id,
        "mission_prompt": prompt,
        "generated_by": "mission_analyst",
        "requirements": requirements,
        "constraints": constraints,
        "assumptions": assumptions,
        "risks": risks,
        "clarifications": [],
    }


def generate_mission_contract(mission_id: str, prompt: str, created_at: str) -> Dict[str, Any]:
    """Convert an immutable mission prompt into a traceable initial contract."""
    if _is_plan_template_mission(prompt):
        return _generate_plan_template_contract(mission_id, prompt)
    if _is_readme_mission(prompt):
        return _generate_readme_contract(mission_id, prompt)

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
            ["Malformed requests receive controlled error responses", "Error responses do not expose stack traces, secrets, or implementation details", "Security-relevant failures are handled consistently with specified or current security guidance"],
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

    clarifications = _clarifications(prompt, constraints, created_at)
    first_excerpt = _source(constraints["technical"] or constraints["functional"], prompt)
    assumptions = [{
        "id": "A-001",
        "statement": "The explicitly named development tools are available in the local validation environment." if constraints["technical"] else "Local filesystem and process execution are available for validation.",
        "traceability": _trace(first_excerpt, "This is a low-risk execution prerequisite and does not select an unspecified framework or interface contract.", _ids(constraints["technical"])),
    }]
    technology_items = _technology_constraint_items(constraints)
    if technology_items:
        guidance_statement = "Current or explicitly specified technology versions are intentional."
        if _current_or_versioned_guidance(prompt):
            guidance_statement = "Current or explicitly specified technology and standards versions are intentional and preserved as mission intent."
        _append_contract_item(
            assumptions,
            "A",
            guidance_statement,
            _trace(
                _source(technology_items, prompt),
                "Battalion assesses engineering readiness and does not determine framework, runtime, platform, library, package, or standards compatibility.",
                _ids(technology_items),
            ),
        )
        _append_contract_item(
            assumptions,
            "A",
            "The engineering team is responsible for selecting mutually compatible dependency versions.",
            _trace(
                _source(technology_items, prompt),
                "Compatibility verification occurs during implementation, testing, and assurance rather than readiness assessment.",
                _ids(technology_items),
            ),
        )
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
    if len(technology_items) >= 2:
        risks.append({
            "id": f"RISK-{len(risks) + 1:03d}", "statement": "Technology compatibility must be validated during implementation and assurance.",
            "traceability": _trace(_source(technology_items, prompt), "Battalion does not maintain compatibility matrices or dependency compatibility graphs.", _ids(technology_items)),
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


def _apply_clarification_trace(requirement: Dict[str, Any], clarification: Dict[str, Any]) -> None:
    trace = requirement.setdefault("traceability", {})
    identifiers = trace.setdefault("clarification_ids", [])
    if clarification["id"] not in identifiers:
        identifiers.append(clarification["id"])
    trace.setdefault("clarification_answers", {})[clarification["id"]] = clarification["answer"]


def _replace_or_append(values: List[str], prefixes: Sequence[str], replacement: str) -> None:
    indexes = [index for index, value in enumerate(values) if any(value.startswith(prefix) for prefix in prefixes)]
    if indexes:
        values[indexes[0]] = replacement
        for index in reversed(indexes[1:]):
            values.pop(index)
    elif replacement not in values:
        values.append(replacement)


def reconcile_mission_contract(contract: Dict[str, Any]) -> List[str]:
    """Apply resolved clarification decisions to existing requirements in place."""
    resolved = [item for item in contract.get("clarifications", []) if item.get("status") in {"resolved", "superseded"}]
    requirements = contract.get("requirements", [])
    updated = set()

    def answer_for(question_text: str):
        return next((item for item in resolved if question_text in item.get("question", "").lower()), None)

    framework = answer_for("framework")
    if framework:
        requirement = next((item for item in requirements if item.get("statement", "").startswith("Create ") and "application" in item.get("statement", "")), None)
        if requirement:
            uses_typescript = any(item.get("statement") == "TypeScript is required." for item in contract.get("constraints", {}).get("technical", []))
            requirement["statement"] = f"Create {framework['answer']}{' TypeScript' if uses_typescript else ''} application"
            _replace_or_append(requirement["acceptance"], ("Application uses ",), f"Application uses {framework['answer']}")
            _apply_clarification_trace(requirement, framework)
            updated.add(requirement["id"])
        assumption = next((item for item in contract.get("assumptions", []) if "selected application framework" in item.get("statement", "")), None)
        if assumption is None:
            assumption = {
                "id": f"A-{len(contract.get('assumptions', [])) + 1:03d}",
                "statement": f"{framework['answer']} is the selected application framework.",
                "traceability": dict(framework["traceability"]),
            }
            contract.setdefault("assumptions", []).append(assumption)
        assumption["traceability"]["clarification_ids"] = [framework["id"]]
        assumption["traceability"]["clarification_answers"] = {framework["id"]: framework["answer"]}

    endpoint = answer_for("endpoint path")
    if endpoint:
        requirement = next((item for item in requirements if "health endpoint" in item.get("statement", "").lower()), None)
        if requirement:
            requirement["statement"] = f"Implement {endpoint['answer']} health endpoint"
            _replace_or_append(
                requirement["acceptance"],
                ("A health endpoint exists", "A valid GET request returns HTTP 200", "GET /"),
                f"GET {endpoint['answer']} returns HTTP 200",
            )
            _apply_clarification_trace(requirement, endpoint)
            updated.add(requirement["id"])

    timestamp_format = answer_for("timestamp format")
    if timestamp_format:
        requirement = next((item for item in requirements if "health endpoint" in item.get("statement", "").lower()), None)
        if requirement:
            _replace_or_append(requirement["acceptance"], ("The response includes a timestamp", "Response timestamp uses "), f"Response timestamp uses {timestamp_format['answer']} format")
            _apply_clarification_trace(requirement, timestamp_format)
            updated.add(requirement["id"])

    owasp = answer_for("owasp")
    if owasp:
        requirement = next((item for item in requirements if item.get("statement") == "Implement secure error handling"), None)
        if requirement:
            _replace_or_append(
                requirement["acceptance"],
                ("Security-relevant failures are handled", "Error handling follows "),
                f"Error handling follows {owasp['answer']}",
            )
            for review in requirement.get("required_reviews", []):
                if review.get("reviewer") == "secops":
                    review["reason"] = f"Validate error handling and disclosure controls against {owasp['answer']}."
            _apply_clarification_trace(requirement, owasp)
            updated.add(requirement["id"])
        for risk in contract.get("risks", []):
            if "OWASP" in risk.get("statement", ""):
                risk["statement"] = f"Security controls must remain aligned with {owasp['answer']}."
                risk.setdefault("traceability", {})["clarification_ids"] = [owasp["id"]]
                risk["traceability"]["clarification_answers"] = {owasp["id"]: owasp["answer"]}

    return sorted(updated)
