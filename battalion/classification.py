"""Deterministic mission classification from configurable attribute catalogs."""

import re
from typing import Any, Dict, List


DEFAULT_ATTRIBUTE_CATALOG = {
    "attributes": [
        {
            "identifier": "REST_API",
            "description": "Mission exposes HTTP API endpoints.",
            "indicators": ["api", "rest", "endpoint", "http", "https", "openapi", "swagger", "route", "status code", "json"],
            "minimum_threshold": 2,
        },
        {
            "identifier": "HTTP_ENDPOINT",
            "description": "Mission defines HTTP endpoint behavior.",
            "indicators": ["endpoint", "route", "http", "https", "get", "post", "put", "patch", "delete", "status code", "http 200"],
            "minimum_threshold": 1,
        },
        {
            "identifier": "USER_INTERFACE",
            "description": "Mission includes user interface work.",
            "indicators": ["react", "angular", "vue", "html", "css", "button", "page", "form", "screen", "frontend", "ui", "user interface"],
            "minimum_threshold": 2,
        },
        {
            "identifier": "DATABASE",
            "description": "Mission includes database or persistence work.",
            "indicators": ["database", "sql", "migration", "schema", "table", "index", "constraint", "postgres", "mysql", "sqlite", "redis"],
            "minimum_threshold": 2,
        },
        {
            "identifier": "SECURITY",
            "description": "Mission includes security-sensitive work.",
            "indicators": ["authentication", "authorization", "jwt", "oidc", "oauth", "owasp", "secrets", "encryption", "security"],
            "minimum_threshold": 1,
        },
        {
            "identifier": "TESTING_REQUIRED",
            "description": "Mission explicitly requires testing.",
            "indicators": ["test", "tests", "testing", "automated tests", "test suite", "happy-path", "negative-path"],
            "minimum_threshold": 1,
        },
        {
            "identifier": "NODE",
            "description": "Mission uses Node.js technology.",
            "indicators": ["node", "nodejs", "node.js", "express", "fastify", "npm"],
            "minimum_threshold": 1,
        },
        {
            "identifier": "TYPESCRIPT",
            "description": "Mission uses TypeScript.",
            "indicators": ["typescript", "tsconfig"],
            "minimum_threshold": 1,
        },
        {
            "identifier": "DOTNET",
            "description": "Mission uses .NET technology.",
            "indicators": [".net", "asp.net", "minimal api", "c#", "entity framework", "dotnet"],
            "minimum_threshold": 1,
        },
        {
            "identifier": "DOCKER",
            "description": "Mission uses Docker or container packaging.",
            "indicators": ["docker", "dockerfile", "container", "containerized", "containerised"],
            "minimum_threshold": 1,
        },
        {
            "identifier": "PUBLIC_ENDPOINT",
            "description": "Mission exposes a public endpoint.",
            "indicators": ["public endpoint", "public api"],
            "minimum_threshold": 1,
        },
        {
            "identifier": "PUBLIC_API",
            "description": "Mission exposes a public API.",
            "indicators": ["public api"],
            "minimum_threshold": 1,
        },
        {
            "identifier": "GET_ONLY",
            "description": "Mission restricts HTTP behavior to GET requests.",
            "indicators": ["get-only", "get only", "allow get requests only", "only get", "get requests only"],
            "minimum_threshold": 1,
        },
        {
            "identifier": "SECURE_ERROR_HANDLING",
            "description": "Mission includes secure error handling or information disclosure constraints.",
            "indicators": ["owasp", "secure error", "malformed", "stack traces", "information disclosure", "do not expose"],
            "minimum_threshold": 1,
        },
        {
            "identifier": "MALICIOUS_TESTING",
            "description": "Mission requires malicious-request validation.",
            "indicators": ["malicious-request", "malicious request", "abuse case"],
            "minimum_threshold": 1,
        },
        {
            "identifier": "AUTHENTICATION",
            "description": "Mission includes authentication or identity work.",
            "indicators": ["authentication", "authorization", "jwt", "login", "token", "identity", "oidc", "oauth"],
            "minimum_threshold": 1,
        },
        {
            "identifier": "CLI",
            "description": "Mission includes command-line interaction.",
            "indicators": ["cli", "command-line", "command line"],
            "minimum_threshold": 1,
        },
        {
            "identifier": "BACKGROUND_PROCESS",
            "description": "Mission includes background processing.",
            "indicators": ["worker", "background", "daemon", "queue"],
            "minimum_threshold": 1,
        },
    ]
}


class MissionClassifier:
    """Classify engineering attributes without applying readiness rules."""

    def __init__(self, catalog: Dict[str, Any]):
        self.catalog = catalog

    def classify(self, mission: Dict[str, Any], ledger: Dict[str, Any]) -> Dict[str, Any]:
        sources = self._contract_sources(mission, ledger)
        attributes = []
        for attribute in self._attributes():
            identifier = str(attribute.get("identifier", "")).strip()
            if not identifier:
                continue
            indicators = [str(value).strip() for value in attribute.get("indicators", []) if str(value).strip()]
            threshold = int(attribute.get("minimum_threshold", 1) or 1)
            evidence = _classification_evidence(sources, indicators)
            matched = sorted({item["indicator"] for item in evidence}, key=lambda value: indicators.index(value))
            hit_count = len(matched)
            classified = hit_count >= threshold
            attributes.append({
                "attribute": identifier,
                "description": attribute.get("description", ""),
                "classification_evidence": evidence,
                "hit_count": hit_count,
                "threshold": threshold,
                "classified": classified,
                "decision": "classified" if classified else "not_classified",
                "evidence": {
                    "classification_evidence": evidence,
                    "hit_count": hit_count,
                    "threshold": threshold,
                    "decision": "Attribute classified." if classified else "Attribute not classified.",
                },
            })
        detected = [item["attribute"] for item in attributes if item["classified"]]
        return {
            "detected_attributes": detected,
            "attributes": attributes,
        }

    def _attributes(self) -> List[Dict[str, Any]]:
        values = self.catalog.get("attributes", [])
        return values if isinstance(values, list) else []

    def _contract_sources(self, mission: Dict[str, Any], ledger: Dict[str, Any]) -> List[Dict[str, str]]:
        sources = []
        _add_source(sources, "mission_prompt", mission.get("mission_prompt") or mission.get("original_prompt") or ledger.get("mission_prompt"))
        _add_source(sources, "mission_objective", mission.get("objective"))
        for requirement in ledger.get("requirements", []) if isinstance(ledger.get("requirements"), list) else []:
            if not isinstance(requirement, dict):
                continue
            _add_source(sources, "requirement", requirement.get("statement"))
            _add_source(sources, "acceptance_criteria", requirement.get("acceptance"))
        for clarification in ledger.get("clarifications", []) if isinstance(ledger.get("clarifications"), list) else []:
            if not isinstance(clarification, dict) or clarification.get("status") not in {"resolved", "superseded", "rejected"}:
                continue
            _add_source(sources, "clarification_answer", clarification.get("answer"))
        return sources


def default_attribute_catalog() -> Dict[str, Any]:
    return {
        "attributes": [
            {
                "identifier": item["identifier"],
                "description": item["description"],
                "indicators": list(item["indicators"]),
                "minimum_threshold": item["minimum_threshold"],
            }
            for item in DEFAULT_ATTRIBUTE_CATALOG["attributes"]
        ]
    }


def _add_source(sources: List[Dict[str, str]], label: str, value: Any) -> None:
    text = _text(value).strip()
    if text:
        sources.append({"source": label, "text": text})


def _classification_evidence(sources: List[Dict[str, str]], indicators: List[str]) -> List[Dict[str, str]]:
    evidence = []
    seen = set()
    for indicator in indicators:
        for source in sources:
            if not _matches_indicator(source["text"], indicator):
                continue
            key = (indicator, source["source"])
            if key in seen:
                continue
            seen.add(key)
            evidence.append({"indicator": indicator, "source": source["source"]})
    return evidence


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values())
    return ""


def _matches_indicator(text: str, indicator: str) -> bool:
    escaped = re.escape(indicator)
    if re.match(r"^[a-z0-9][a-z0-9 +#.-]*[a-z0-9#]$", indicator, flags=re.IGNORECASE):
        pattern = rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])"
    else:
        pattern = escaped
    return re.search(pattern, text, flags=re.IGNORECASE) is not None
