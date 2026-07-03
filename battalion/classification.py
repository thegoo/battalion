"""Deterministic mission classification from external attribute catalogs."""

import re
from pathlib import Path
from typing import Any, Dict, List

import yaml


ATTRIBUTE_SCHEMA_VERSION = "battalion.attributes.v1"
DEFAULT_CATALOG_PATH = Path(__file__).with_name("attributes.yml")


class AttributeCatalogLoader:
    """Load and validate mission classification attribute catalogs."""

    def __init__(self, path: Path = None):
        self.path = Path(path) if path is not None else DEFAULT_CATALOG_PATH

    def load(self) -> Dict[str, Any]:
        try:
            catalog = parse_attribute_catalog(self.path.read_text(encoding="utf-8"))
            return normalize_attribute_catalog(catalog)
        except OSError as exc:
            raise ValueError(f"cannot read {self.path.name}: {exc}") from exc
        except ValueError as exc:
            raise ValueError(f"attribute catalog must be valid YAML conforming to {ATTRIBUTE_SCHEMA_VERSION}: {exc}") from exc


class MissionClassifier:
    """Classify engineering attributes without applying readiness rules."""

    def __init__(self, catalog: Dict[str, Any]):
        self.catalog = normalize_attribute_catalog(catalog)

    def classify(self, mission: Dict[str, Any], ledger: Dict[str, Any]) -> Dict[str, Any]:
        corpus = MissionCorpus.from_mission_contract(mission, ledger)
        attributes = []
        for attribute in self.catalog["attributes"]:
            indicators = attribute["indicators"]
            threshold = attribute["threshold"]
            evidence = _classification_evidence(corpus.sources, indicators)
            matched = sorted({item["indicator"] for item in evidence}, key=lambda value: indicators.index(value))
            hit_count = len(matched)
            classified = hit_count >= threshold
            attributes.append({
                "attribute": attribute["identifier"],
                "description": attribute["description"],
                "threshold": threshold,
                "matched_indicators": matched,
                "hit_count": hit_count,
                "classified": classified,
                "decision": "classified" if classified else "not_classified",
                "classification_evidence": evidence,
                "evidence": {
                    "classification_evidence": evidence,
                    "hit_count": hit_count,
                    "threshold": threshold,
                    "decision": "Attribute classified." if classified else "Attribute not classified.",
                },
            })
        detected = [item["attribute"] for item in attributes if item["classified"]]
        return {
            "schema_version": self.catalog["schema_version"],
            "detected_attributes": detected,
            "attributes": attributes,
        }


class MissionCorpus:
    """Structured text sources used by MissionClassifier."""

    def __init__(self, sources: List[Dict[str, str]]):
        self.sources = sources

    @classmethod
    def from_mission_contract(cls, mission: Dict[str, Any], ledger: Dict[str, Any]) -> "MissionCorpus":
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
        return cls(sources)


def default_attribute_catalog() -> Dict[str, Any]:
    return AttributeCatalogLoader(DEFAULT_CATALOG_PATH).load()


def write_default_attribute_catalog(path: Path) -> None:
    path.write_text(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"), encoding="utf-8")


def parse_attribute_catalog(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise ValueError("attribute catalog is empty")
    if stripped.startswith("{"):
        raise ValueError("JSON/object-literal catalogs are not accepted")
    try:
        catalog = yaml.safe_load(stripped)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    return catalog


def normalize_attribute_catalog(catalog: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(catalog, dict):
        raise ValueError("attribute catalog must be an object")
    schema_version = catalog.get("schema_version")
    if schema_version != ATTRIBUTE_SCHEMA_VERSION:
        raise ValueError(f"unsupported attribute catalog schema_version: {schema_version!r}")
    raw_attributes = catalog.get("attributes")
    if isinstance(raw_attributes, dict):
        items = [
            {"identifier": identifier, **definition}
            for identifier, definition in raw_attributes.items()
            if isinstance(definition, dict)
        ]
    elif isinstance(raw_attributes, list):
        items = raw_attributes
    else:
        raise ValueError("attribute catalog must contain an attributes mapping or list")

    attributes = []
    seen = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"attribute catalog entry {index} must be an object")
        identifier = str(item.get("identifier", "")).strip()
        if not identifier:
            raise ValueError(f"attribute catalog entry {index} is missing identifier")
        if identifier in seen:
            raise ValueError(f"attribute catalog contains duplicate identifier: {identifier}")
        seen.add(identifier)
        description = str(item.get("description", "")).strip()
        if not description:
            raise ValueError(f"attribute {identifier} is missing description")
        indicators = [str(value).strip() for value in item.get("indicators", []) if str(value).strip()]
        if not indicators:
            raise ValueError(f"attribute {identifier} must define at least one indicator")
        threshold = item.get("threshold")
        try:
            threshold = int(threshold)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"attribute {identifier} threshold must be an integer") from exc
        if threshold < 1:
            raise ValueError(f"attribute {identifier} threshold must be at least 1")
        attributes.append({
            "identifier": identifier,
            "description": description,
            "indicators": indicators,
            "threshold": threshold,
        })
    return {"schema_version": ATTRIBUTE_SCHEMA_VERSION, "attributes": attributes}


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
