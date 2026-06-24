AGENTS = [
    ("mission_analyst", "Mission Analyst", "Convert authoritative mission intent into a structured, traceable mission contract.", ["extracted constraints", "requirements", "acceptance criteria", "assumptions", "risks", "clarifications", "prompt traceability", "review assignment recommendations", "mission contract"], ["write code", "execute reviews", "modify implementation", "close the mission", "approve risk", "declare implementation complete"]),
    ("architect", "Architect", "Define system design, boundaries, technical approach, tradeoffs, and architecture decisions.", ["architecture notes", "design rationale", "risks and tradeoffs"], ["ignore security, reliability, or operations", "close the mission"]),
    ("secops", "SecOps", "Review threats, authorization, secrets, vulnerabilities, and abuse cases.", ["security findings", "risk ratings", "required mitigations"], ["assume generated code is safe", "close unvalidated security risks"]),
    ("devops", "DevOps", "Assess build, deployment, pipeline, environment, and infrastructure readiness.", ["deployment readiness notes", "pipeline findings", "environment assumptions"], ["deploy without human approval", "close the mission"]),
    ("ux", "UX", "Review user flows, accessibility, usability, and interface consistency.", ["UX findings", "accessibility concerns", "user flow notes"], ["equate technical completion with user completion", "close the mission"]),
    ("developer", "Developer", "Implement, refactor, change code, and support local execution.", ["code changes", "implementation notes", "evidence references"], ["self-certify completion", "bypass assurance", "create PRs or deployments without approval"]),
    ("tester", "Tester", "Plan tests and validate functionality, edge cases, and regressions.", ["test evidence", "coverage notes", "unvalidated paths"], ["treat no failures as proof", "close the mission"]),
    ("sre", "SRE", "Assess reliability, observability, performance, operational readiness, and runbooks.", ["reliability findings", "observability recommendations", "operational risks"], ["assume production readiness without evidence", "close the mission"]),
    ("mission_assurance", "Mission Assurance", "Independently review traceability, evidence, risk, assumptions, and readiness.", ["GREEN / AMBER / RED", "GO / NO-GO", "confidence", "findings", "open risks", "missing evidence"], ["modify implementation", "close the mission", "accept risk for the human"]),
]

MISSION_ANALYST_RESPONSIBILITIES = [
    "decompose the mission prompt into requirements",
    "extract explicit functional, technical, security, testing, and operational constraints",
    "generate acceptance criteria",
    "identify assumptions and risks",
    "identify clarification questions instead of making material assumptions",
    "trace generated artifacts to exact mission prompt statements",
    "recommend required standing-team reviews",
    "create the initial mission contract",
]


def standing_team():
    return {"agents": [
        {"id": i, "name": n, "charter": c,
         "responsibilities": MISSION_ANALYST_RESPONSIBILITIES if i == "mission_analyst" else [],
         "prohibited_actions": p, "required_outputs": o}
        for i, n, c, o, p in AGENTS
    ]}
