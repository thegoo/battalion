"""Mission intake synthesis boundaries.

Intake synthesis only structures human mission text. Plan generation remains
owned by the deterministic mission analyst and plan renderer.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Protocol


AI_ASSISTED_INTAKE_FLAG = "--ai-assisted-intake"
TOO_COMPLEX_MESSAGE = (
    "Deterministic intake cannot structure this mission confidently. "
    f"Rerun with {AI_ASSISTED_INTAKE_FLAG} to opt in to AI-assisted intake synthesis."
)


@dataclass(frozen=True)
class RequestedArtifact:
    path: str
    artifact_type: str
    source_excerpt: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "path": self.path,
            "artifact_type": self.artifact_type,
            "source_excerpt": self.source_excerpt,
        }


@dataclass(frozen=True)
class IntakeSynthesis:
    mode: str
    original_requirement: str
    requested_artifacts: List[RequestedArtifact] = field(default_factory=list)
    traceability: Dict[str, str] = field(default_factory=dict)
    provider: str = "deterministic"

    def to_dict(self) -> Dict[str, object]:
        return {
            "schema_version": "battalion.intake.v1",
            "mode": self.mode,
            "provider": self.provider,
            "original_requirement": self.original_requirement,
            "requested_artifacts": [artifact.to_dict() for artifact in self.requested_artifacts],
            "traceability": dict(self.traceability),
        }


class MissionIntakeSynthesizer(Protocol):
    def synthesize(self, requirement: str) -> IntakeSynthesis:
        """Return structured mission intent without changing the human text."""


def _markdown_artifacts(requirement: str) -> List[RequestedArtifact]:
    artifacts = []
    seen = set()
    for match in re.finditer(r"\b[A-Za-z0-9][A-Za-z0-9_.-]*\.md\b", requirement):
        path = match.group(0)
        key = path.lower()
        if key in seen:
            continue
        seen.add(key)
        artifacts.append(RequestedArtifact(
            path=path,
            artifact_type="markdown_document",
            source_excerpt=requirement,
        ))
    return artifacts


def deterministic_intake_too_complex(requirement: str) -> bool:
    text = " ".join(requirement.split())
    if len(text) > 900:
        return True
    clause_count = len(re.findall(r"\b(?:and|or|but|especially|expected|preserve|required|include)\b", text, flags=re.IGNORECASE))
    return clause_count >= 16


class DeterministicMissionIntakeSynthesizer:
    def synthesize(self, requirement: str) -> IntakeSynthesis:
        if deterministic_intake_too_complex(requirement):
            raise ValueError(TOO_COMPLEX_MESSAGE)
        return IntakeSynthesis(
            mode="deterministic",
            original_requirement=requirement,
            requested_artifacts=_markdown_artifacts(requirement),
            traceability={"source": "mission_prompt", "prompt_excerpt": requirement},
        )


class StubAiAssistedMissionIntakeSynthesizer:
    """Provider boundary for future AI-assisted synthesis.

    The stub deliberately performs only deterministic local extraction. It proves
    the opt-in route and records the boundary without requiring an AI provider.
    """

    def synthesize(self, requirement: str) -> IntakeSynthesis:
        return IntakeSynthesis(
            mode="ai_assisted",
            provider="stub",
            original_requirement=requirement,
            requested_artifacts=_markdown_artifacts(requirement),
            traceability={"source": "mission_prompt", "prompt_excerpt": requirement},
        )


def synthesize_mission_intake(requirement: str, ai_assisted: bool = False) -> IntakeSynthesis:
    synthesizer: MissionIntakeSynthesizer
    if ai_assisted:
        synthesizer = StubAiAssistedMissionIntakeSynthesizer()
    else:
        synthesizer = DeterministicMissionIntakeSynthesizer()
    return synthesizer.synthesize(requirement)
