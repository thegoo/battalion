from dataclasses import dataclass, field
from typing import Any, Dict, List


VALID_STATUSES = {
    "proposed", "planned", "in_progress", "completed", "deferred",
    "rejected", "accepted_risk",
}
FINAL_STATUSES = {"completed", "deferred", "rejected", "accepted_risk"}
VALID_REVIEW_STATUSES = {"pending", "completed"}


@dataclass
class Review:
    reviewer: str
    status: str = "pending"
    reason: str = ""

    def to_dict(self) -> Dict[str, str]:
        result = {"reviewer": self.reviewer, "status": self.status}
        if self.reason:
            result["reason"] = self.reason
        return result


@dataclass
class Requirement:
    id: str
    statement: str
    status: str = "proposed"
    owner: str = "mission_analyst"
    acceptance: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    required_reviews: List[Review] = field(default_factory=list)
    traceability: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "Requirement":
        if not isinstance(value, dict):
            raise ValueError("requirement must be an object")
        required = ("id", "statement", "status", "acceptance", "evidence", "required_reviews")
        missing = [name for name in required if name not in value]
        if missing:
            raise ValueError("requirement missing " + ", ".join(missing))
        lists = ("acceptance", "evidence", "risks", "assumptions", "required_reviews")
        for name in lists:
            if not isinstance(value.get(name, []), list):
                raise ValueError(f"requirement {value['id']} {name} must be a list")
        data = {name: value[name] for name in cls.__dataclass_fields__ if name in value and name != "required_reviews"}
        data["required_reviews"] = [Review(**review) for review in value["required_reviews"]]
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        result = {name: getattr(self, name) for name in self.__dataclass_fields__}
        result["required_reviews"] = [review.to_dict() for review in self.required_reviews]
        return result


@dataclass
class AssuranceResult:
    status: str
    recommendation: str
    confidence: int
    findings: List[str]
    clarification_counts: Dict[str, int] = field(default_factory=dict)
    engineering_result: Dict[str, Any] = field(default_factory=dict)
    governance_result: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.recommendation == "GO" and self.status != "GREEN":
            raise ValueError("GO is only valid when assurance status is GREEN")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "recommendation": self.recommendation,
            "confidence": self.confidence,
            "findings": self.findings,
            "clarification_counts": self.clarification_counts,
            "engineering_result": self.engineering_result,
            "governance_result": self.governance_result,
        }
